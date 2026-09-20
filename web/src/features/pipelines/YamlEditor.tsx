import { useRef, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection } from '@codemirror/view';
import { EditorState, Compartment } from '@codemirror/state';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { yaml } from '@codemirror/lang-yaml';
import { foldGutter, indentOnInput, bracketMatching, foldKeymap } from '@codemirror/language';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import { lintGutter } from '@codemirror/lint';
import { Alert, Button, Tooltip, Space } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import type { ValidationError } from '@/types';

/**
 * v5 (2026-08): 浅色主题 —— 与 DAG 画布的 n8n 风格统一。
 * 此前用 oneDark 深色主题，与浅色画布并排时割裂感强（用户反馈"样式保持统一"）。
 * 移除 oneDark 后 CodeMirror 回落到默认浅色语法高亮（defaultHighlightStyle fallback），
 * 这里仅补充与 nodeTokens.INK 对齐的界面色（gutter/activeLine/选区等）。
 */

export interface YamlEditorRef {
  /** 滚动到指定行（1-indexed），并临时高亮 2s */
  scrollToLine: (line: number) => void;
}

/**
 * v5 (2026-08): 浅色 CodeMirror 主题 —— 色值与 nodeTokens.INK（n8n 风格）对齐：
 * 白底、slate 系 gutter/文本、淡灰 activeLine，与 DAG 画布并排时视觉统一
 */
const lightTheme = EditorView.theme({
  '&': { backgroundColor: '#FFFFFF', color: '#334155' },
  '.cm-content': { fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace', fontSize: 13 },
  '.cm-gutters': { backgroundColor: '#F8FAFC', color: '#94A3B8', border: 'none', borderRight: '1px solid #E2E8F0' },
  '.cm-activeLine': { backgroundColor: 'rgba(148, 163, 184, 0.08)' },
  '.cm-activeLineGutter': { backgroundColor: 'rgba(148, 163, 184, 0.14)' },
  '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': { backgroundColor: '#BFDBFE' },
  '.cm-cursor': { borderLeftColor: '#FF6D5A' },
  '.cm-matchingBracket': { backgroundColor: 'rgba(148, 163, 184, 0.25)', outline: 'none' },
});

export interface YamlEditorProps {
  /** 初始 YAML 文本 */
  value: string;
  /** 内容变化回调（已 debounce） */
  onChange: (value: string) => void;
  /** YAML 校验错误（统一结构：message, line?, column?, path?） */
  error?: ValidationError | null;
  /** 编辑器高度 */
  height?: string | number;
  /** 是否只读 */
  readOnly?: boolean;
  /** 光标所在行包含 task name 时回调 */
  onCursorTaskChange?: (taskId: string | null) => void;
  /** 保存回调；参数为编辑器当前完整内容（避免父组件读取 debounce 未落定的旧值） */
  onSave?: (content?: string) => void;
  /** 是否正在保存 */
  saving?: boolean;
}

/** CodeMirror YAML 编辑器组件 */
const YamlEditor = forwardRef<YamlEditorRef, YamlEditorProps>(function YamlEditor({ value, onChange, error, height = '100%', readOnly = false, onCursorTaskChange, onSave, saving }, ref) {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout>>();

  onChangeRef.current = onChange;
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const onCursorTaskChangeRef = useRef(onCursorTaskChange);
  onCursorTaskChangeRef.current = onCursorTaskChange;

  // 暴露 scrollToLine 给父组件
  useImperativeHandle(ref, () => ({
    scrollToLine(line: number) {
      const view = viewRef.current;
      if (!view) return;
      const lineObj = view.state.doc.line(Math.min(Math.max(line, 1), view.state.doc.lines));
      view.dispatch({
        selection: { anchor: lineObj.from },
        effects: EditorView.scrollIntoView(lineObj.from, { y: 'center' }),
      });
      // 临时高亮目标行 2s — 通过 DOM 操作
      const lineEls = view.dom.querySelectorAll('.cm-line');
      const targetEl = lineEls[lineObj.number - 1];
      if (targetEl) {
        targetEl.classList.add('cm-highlight-line');
        setTimeout(() => targetEl.classList.remove('cm-highlight-line'), 2000);
      }
    },
  }), []);

  // debounce 的 onChange
  const debouncedOnChange = useCallback((val: string) => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      onChangeRef.current(val);
    }, 300);
  }, []);

  // v7 (2026-08): 保存前必须先冲刷 debounce。
  // 旧实现 onChange 有 300ms debounce，而 onSave 立即触发父组件的 handleSave，
  // 父组件读到的 yamlText 还是旧值 —— 「快速输入后马上 Ctrl+S/点保存」会静默
  // 丢掉最后一段输入。这里同步把当前文档交给父组件，并把内容作为参数传给 onSave。
  const saveRef = useRef<() => void>(() => {});
  saveRef.current = () => {
    const view = viewRef.current;
    if (!view) return;
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    const current = view.state.doc.toString();
    onChangeRef.current(current);
    onSaveRef.current?.(current);
  };

  useEffect(() => {
    if (!editorRef.current) return;

    const readOnlyCompartment = new Compartment();

    const updateListener = EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        debouncedOnChange(update.state.doc.toString());
      }
      // 检测光标所在行是否包含 `- name: <taskId>`
      if (update.selectionSet || update.docChanged) {
        const pos = update.state.selection.main.head;
        const line = update.state.doc.lineAt(pos);
        const match = line.text.match(/-\s+name:\s+(\S+)/);
        onCursorTaskChangeRef.current?.(match ? match[1] : null);
      }
    });

    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        highlightActiveLineGutter(),
        drawSelection(),
        history(),
        foldGutter(),
        indentOnInput(),
        bracketMatching(),
        closeBrackets(),
        highlightSelectionMatches(),
        lintGutter(),
        yaml(),
        // v5 (2026-08): 移除 oneDark，改用与画布统一的浅色主题
        lightTheme,
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...foldKeymap,
          ...closeBracketsKeymap,
          ...searchKeymap,
          indentWithTab,
          { key: 'Mod-s', run: () => { saveRef.current(); return true; } },
        ]),
        readOnlyCompartment.of(EditorState.readOnly.of(readOnly)),
        updateListener,
        EditorView.lineWrapping,
        EditorView.theme({
          '.cm-highlight-line': {
            backgroundColor: 'rgba(255, 255, 0, 0.15)',
            display: 'inline',
          },
        }),
      ],
    });

    const view = new EditorView({
      state,
      parent: editorRef.current,
    });

    viewRef.current = view;

    return () => {
      // v7 (2026-08): 卸载时清掉未触发的 debounce，避免组件关闭后回调仍触发父组件 setState
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 外部 value 变化时同步到编辑器（仅当内容不同时）
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const currentDoc = view.state.doc.toString();
    if (currentDoc !== value) {
      view.dispatch({
        changes: { from: 0, to: currentDoc.length, insert: value },
      });
    }
  }, [value]);

  // 直接使用外部传入的 error，不再维护独立的 internalError（v2 移除内部无效状态）

  return (
    <div className="flex flex-col h-full">
      {/* 工具栏 —— v5 (2026-08): 浅色化，与页面工具栏（bg-gray-50 白系）统一 */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-[#E2E8F0] shrink-0">
        <span className="text-xs text-[#64748B] font-medium">YAML 编辑器</span>
        <Space size="small">
          {onSave && (
            <Tooltip title="保存 (Ctrl+S)">
              <Button type="primary" size="small" icon={<SaveOutlined />} onClick={() => saveRef.current()} loading={saving}>
                保存
              </Button>
            </Tooltip>
          )}
        </Space>
      </div>

      {/* 编辑器区域 */}
      <div ref={editorRef} className="flex-1 min-h-0 overflow-auto" style={{ height }} />

      {/* v1 (2026-07): issue #195 — 错误信息统一展示 message + 可选 line/column/path */}
      {error && (
        <div className="shrink-0 border-t border-[#E2E8F0]">
          <Alert
            type="error"
            showIcon
            banner
            message={
              <span className="text-xs font-mono">
                {error.line != null && error.column != null
                  ? `行 ${error.line}:${error.column} — `
                  : ''}
                {error.path ? `${error.path}: ` : ''}
                {error.message}
              </span>
            }
          />
        </div>
      )}
    </div>
  );
});

export default YamlEditor;
