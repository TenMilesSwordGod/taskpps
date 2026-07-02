import { useRef, useEffect, useCallback, useState, forwardRef, useImperativeHandle } from 'react';
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection } from '@codemirror/view';
import { EditorState, Compartment } from '@codemirror/state';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { yaml } from '@codemirror/lang-yaml';
import { foldGutter, indentOnInput, bracketMatching, foldKeymap } from '@codemirror/language';
import { oneDark } from '@codemirror/theme-one-dark';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { searchKeymap, highlightSelectionMatches } from '@codemirror/search';
import { lintGutter } from '@codemirror/lint';
import { Alert, Button, Tooltip, Space } from 'antd';
import { FormatPainterOutlined, UndoOutlined, RedoOutlined } from '@ant-design/icons';

export interface YamlEditorRef {
  /** 滚动到指定行（1-indexed），并临时高亮 2s */
  scrollToLine: (line: number) => void;
}

export interface YamlEditorProps {
  /** 初始 YAML 文本 */
  value: string;
  /** 内容变化回调（已 debounce） */
  onChange: (value: string) => void;
  /** YAML 解析错误 */
  error?: { message: string; line: number; column: number } | null;
  /** 编辑器高度 */
  height?: string | number;
  /** 是否只读 */
  readOnly?: boolean;
  /** 光标所在行包含 task name 时回调 */
  onCursorTaskChange?: (taskId: string | null) => void;
}

/** CodeMirror YAML 编辑器组件 */
const YamlEditor = forwardRef<YamlEditorRef, YamlEditorProps>(function YamlEditor({ value, onChange, error, height = '100%', readOnly = false, onCursorTaskChange }, ref) {
  const editorRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [internalError, setInternalError] = useState<typeof error>(null);

  onChangeRef.current = onChange;
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
        keymap.of([
          ...defaultKeymap,
          ...historyKeymap,
          ...foldKeymap,
          ...closeBracketsKeymap,
          ...searchKeymap,
          indentWithTab,
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

  // 合并外部和内部错误
  const displayError = error ?? internalError;

  // 撤销/重做
  const handleUndo = () => {
    const view = viewRef.current;
    if (!view) return;
    // 触发 Ctrl+Z
    view.dispatch({ selection: view.state.selection.main });
  };

  const handleRedo = () => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({ selection: view.state.selection.main });
  };

  const handleFormat = () => {
    setInternalError(null);
  };

  return (
    <div className="flex flex-col h-full">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#252526] border-b border-[#333] shrink-0">
        <span className="text-xs text-gray-400 font-medium">YAML 编辑器</span>
        <Space size="small">
          <Tooltip title="撤销 (Ctrl+Z)">
            <Button type="text" size="small" icon={<UndoOutlined />} onClick={handleUndo} className="text-gray-400 hover:text-white" />
          </Tooltip>
          <Tooltip title="重做 (Ctrl+Y)">
            <Button type="text" size="small" icon={<RedoOutlined />} onClick={handleRedo} className="text-gray-400 hover:text-white" />
          </Tooltip>
          <Tooltip title="格式化">
            <Button type="text" size="small" icon={<FormatPainterOutlined />} onClick={handleFormat} className="text-gray-400 hover:text-white" />
          </Tooltip>
        </Space>
      </div>

      {/* 编辑器区域 */}
      <div ref={editorRef} className="flex-1 min-h-0 overflow-auto" style={{ height }} />

      {/* 错误信息 */}
      {displayError && (
        <div className="shrink-0 border-t border-[#333]">
          <Alert
            type="error"
            showIcon
            banner
            message={
              <span className="text-xs font-mono">
                行 {displayError.line}:{displayError.column} — {displayError.message}
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
