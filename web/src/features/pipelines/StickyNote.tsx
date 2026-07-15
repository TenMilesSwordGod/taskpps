import { useState, useCallback, memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { X } from 'lucide-react';
import { FONT_MONO } from './nodes/nodeTokens';
import { STICKY_COLORS } from './stores/pipelineEditorStore';
import type { StickyColor, StickyNoteItem } from './stores/pipelineEditorStore';

/**
 * 便签节点 — ReactFlow 自定义节点类型
 *
 * 设计决策：
 * - 默认尺寸 240×160px，可拖拽右下角调整（最小 120×80px）
 * - 双击进入 Markdown 源码编辑模式，失焦后渲染格式文本
 * - 5 种颜色（黄/蓝/绿/粉/橙），通过点击 header 圆点切换
 * - 拖拽至 Task 节点 20px 内自动吸附（snapToNodeId）
 * - 右上角 × 按钮删除
 * - 便签为纯视觉元素，不属于 Pipeline 数据模型 → 由 store 管理
 */

export interface StickyNoteData {
  content: string;
  color: StickyColor;
  width: number;
  height: number;
  snapToNodeId?: string | null;
  onDelete?: (id: string) => void;
  onUpdate?: (id: string, data: Partial<StickyNoteItem>) => void;
}

/** 简单 Markdown 渲染 — 支持 **粗体** `代码` - 列表项 */
function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`([^`]+)`/g, '<code style="font-family:monospace;background:rgba(0,0,0,0.08);padding:1px 4px;border-radius:3px;font-size:11px">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li style="margin-left:12px">$1</li>')
    .replace(/\n/g, '<br/>');
}

const DEFAULT_W = 240;
const DEFAULT_H = 160;
const MIN_W = 120;
const MIN_H = 80;

function StickyNoteComponent({
  id,
  data,
}: {
  id: string;
  data: StickyNoteData;
}) {
  const colors = STICKY_COLORS[data.color] ?? STICKY_COLORS.yellow;
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(data.content);
  // v1 (2026-07): 初始尺寸从 data 读取，未设置时用默认值
  const [size, setSize] = useState({
    w: data.width || DEFAULT_W,
    h: data.height || DEFAULT_H,
  });

  const handleDoubleClick = useCallback(() => {
    setEditText(data.content);
    setEditing(true);
  }, [data.content]);

  const handleBlur = useCallback(() => {
    setEditing(false);
    data.onUpdate?.(id, { content: editText });
  }, [editText, id, data]);

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      data.onDelete?.(id);
    },
    [id, data],
  );

  const handleColorCycle = useCallback(() => {
    const keys = Object.keys(STICKY_COLORS) as StickyColor[];
    const idx = keys.indexOf(data.color);
    const next = keys[(idx + 1) % keys.length];
    data.onUpdate?.(id, { color: next });
  }, [data.color, id, data]);

  // 拖拽调整尺寸
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const startW = size.w;
      const startH = size.h;

      const onMove = (ev: MouseEvent) => {
        const newW = Math.max(MIN_W, startW + (ev.clientX - startX));
        const newH = Math.max(MIN_H, startH + (ev.clientY - startY));
        setSize({ w: newW, h: newH });
      };

      const onUp = () => {
        const finalSize = { w: size.w, h: size.h };
        setSize((prev) => {
          finalSize.w = prev.w;
          finalSize.h = prev.h;
          return prev;
        });
        data.onUpdate?.(id, { width: finalSize.w, height: finalSize.h });
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [id, data, size],
  );

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        className="!w-1.5 !h-1.5 !bg-transparent !border-0"
      />
      <div
        onDoubleClick={handleDoubleClick}
        className="relative flex flex-col rounded-lg select-none"
        style={{
          width: size.w,
          height: size.h,
          backgroundColor: colors.bg,
          border: `1.5px solid ${colors.border}`,
          boxShadow: '0 2px 6px rgba(0,0,0,0.08)',
          cursor: editing ? 'text' : 'grab',
        }}
      >
        {/* Header: 颜色圆点 + 分隔线 + 删除按钮 */}
        <div
          className="flex items-center shrink-0 px-2"
          style={{ height: 28 }}
        >
          <button
            onClick={handleColorCycle}
            className="flex-shrink-0 rounded-full cursor-pointer border-0"
            style={{
              width: 10,
              height: 10,
              backgroundColor: colors.dot,
            }}
            title="切换便签颜色"
          />
          <div
            className="flex-1 mx-2"
            style={{
              borderTop: `1px dashed ${colors.border}`,
            }}
          />
          <button
            onClick={handleDelete}
            className="flex items-center justify-center rounded hover:bg-black/5 transition-colors border-0 bg-transparent cursor-pointer"
            style={{ width: 20, height: 20 }}
          >
            <X size={14} color="#868E96" />
          </button>
        </div>

        {/* Body: 编辑/渲染模式 */}
        <div className="flex-1 min-h-0 overflow-hidden px-2 pb-2">
          {editing ? (
            <textarea
              autoFocus
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onBlur={handleBlur}
              onPointerDown={(e) => e.stopPropagation()}
              className="w-full h-full resize-none border-0 outline-none bg-transparent"
              style={{
                fontFamily: FONT_MONO,
                fontSize: 12,
                lineHeight: 1.6,
                color: '#212529',
              }}
            />
          ) : (
            <div
              className="w-full h-full overflow-auto"
              style={{
                fontFamily: FONT_MONO,
                fontSize: 12,
                lineHeight: 1.6,
                color: '#212529',
              }}
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(data.content || '双击编辑...'),
              }}
            />
          )}
        </div>

        {/* Resize handle — 右下角 */}
        <div
          onMouseDown={handleResizeStart}
          onPointerDown={(e) => e.stopPropagation()}
          className="absolute right-0 bottom-0 cursor-se-resize"
          style={{ width: 16, height: 16 }}
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            style={{ opacity: 0.4 }}
          >
            <line x1="11" y1="1" x2="1" y2="11" stroke="#868E96" strokeWidth="1.5" />
            <line x1="11" y1="6" x2="6" y2="11" stroke="#868E96" strokeWidth="1.5" />
            <line x1="11" y1="11" x2="11" y2="11" stroke="#868E96" strokeWidth="1.5" />
          </svg>
        </div>
      </div>
    </>
  );
}

export default memo(StickyNoteComponent);
