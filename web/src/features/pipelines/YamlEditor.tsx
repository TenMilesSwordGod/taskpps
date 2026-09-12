import { useRef, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react';
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, hoverTooltip } from '@codemirror/view';
import { EditorState, Compartment } from '@codemirror/state';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { yaml } from '@codemirror/lang-yaml';
import { foldGutter, indentOnInput, bracketMatching, foldKeymap } from '@codemirror/language';
import { oneDark } from '@codemirror/theme-one-dark';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import { lintGutter } from '@codemirror/lint';
import { Alert, Button, Tooltip, Space } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import type { ValidationError } from '@/types';
import {
  buildVariableTooltipDom,
  findVariableAt,
  resolveVariableInfo,
  type AgentVariableSource,
  type CredentialVariableSource,
  type YamlVariableIndex,
} from '@/utils/yamlVariables';

export interface YamlEditorRef {
  /** 滚动到指定行（1-indexed），并临时高亮 2s */
  scrollToLine: (line: number) => void;
}

/** 变量悬浮所需的数据：YAML 上下文索引 + 调用方注入的项目配置 */
export interface VariableHoverData {
  index: YamlVariableIndex;
  agents?: Map<string, AgentVariableSource>;
  credentials?: Map<string, CredentialVariableSource>;
  /** 凭据不可见（非管理员）时不误报"未找到" */
  credentialsUnavailable?: boolean;
}

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
  /** 保存回调 */
  onSave?: () => void;
  /** 是否正在保存 */
  saving?: boolean;
  /** v3 (2026-09): ${...} 悬浮解析数据；不传则无悬浮提示 */
  variableHover?: VariableHoverData;
}

/** CodeMirror YAML 编辑器组件 */
const YamlEditor = forwardRef<YamlEditorRef, YamlEditorProps>(function YamlEditor({ value, onChange, error, height = '100%', readOnly = false, onCursorTaskChange, onSave, saving, variableHover }, ref) {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout>>();

  onChangeRef.current = onChange;
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const onCursorTaskChangeRef = useRef(onCursorTaskChange);
  onCursorTaskChangeRef.current = onCursorTaskChange;
  // v3 (2026-09): 悬浮扩展在挂载时创建一次，通过 ref 读取最新解析数据，
  // 避免每次 value/项目配置变化都重建 CodeMirror extension
  const variableHoverRef = useRef(variableHover);
  variableHoverRef.current = variableHover;

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
        oneDark,
        // v3 (2026-09): ${...} 悬浮展示解析值；数据通过 ref 读取，
        // 扩展本身只创建一次，避免编辑器频繁重建
        hoverTooltip((view, pos) => {
          const data = variableHoverRef.current;
          if (!data) return null;
          const line = view.state.doc.lineAt(pos);
          const found = findVariableAt(line.text, pos - line.from);
          if (!found) return null;
          const info = resolveVariableInfo(found.expression, data.index, {
            lineNumber: line.number,
            agents: data.agents,
            credentials: data.credentials,
            credentialsUnavailable: data.credentialsUnavailable,
          });
          return {
            pos: line.from + found.from,
            end: line.from + found.to,
            create: () => ({ dom: buildVariableTooltipDom(info) }),
          };
        }),
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...foldKeymap,
          ...closeBracketsKeymap,
          ...searchKeymap,
          indentWithTab,
          { key: 'Mod-s', run: () => { onSaveRef.current?.(); return true; } },
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
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#252526] border-b border-[#333] shrink-0">
        <span className="text-xs text-gray-400 font-medium">YAML 编辑器</span>
        <Space size="small">
          {onSave && (
            <Tooltip title="保存 (Ctrl+S)">
              <Button type="primary" size="small" icon={<SaveOutlined />} onClick={onSave} loading={saving}>
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
        <div className="shrink-0 border-t border-[#333]">
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
            className="!bg-[#2d1b1b] !border-[#5a2020]"
          />
        </div>
      )}
    </div>
  );
});

export default YamlEditor;
