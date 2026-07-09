import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { INK, FONT_MONO, NODE_SIZE } from './nodeTokens';

export type PostVariant = 'on_fail' | 'on_success' | 'always';

interface PostTaskNodeData {
  label: string;
  variant: PostVariant;
  parentTaskId: string;
  [key: string]: unknown;
}

const VARIANT_STYLE: Record<PostVariant, {
  color: string;
  tag: string;
}> = {
  on_fail: { color: '#EA580C', tag: 'ON_FAIL' },
  on_success: { color: '#16A34A', tag: 'ON_OK' },
  always: { color: '#64748B', tag: 'ALWAYS' },
};

/**
 * Post 任务节点 —— 工程蓝图风格极简条
 * 左侧色条 + 等宽名称 + 变体标签
 */
function PostTaskNodeComponent({ data }: { data: PostTaskNodeData }) {
  const { label, variant } = data;
  const s = VARIANT_STYLE[variant];

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        className="!w-1 !h-1 !bg-slate-300 !border-0 !-top-[2px]"
      />

      <div
        className="flex items-center gap-1.5 bg-white select-none whitespace-nowrap"
        style={{
          width: NODE_SIZE.POST_W,
          height: NODE_SIZE.POST_H,
          padding: '0 6px 0 0',
          border: `1px solid ${INK.border}`,
          borderRadius: 3,
          fontFamily: FONT_MONO,
        }}
      >
        {/* 左侧变体色条 */}
        <div
          style={{
            width: 2,
            alignSelf: 'stretch',
            backgroundColor: s.color,
            borderTopLeftRadius: 3,
            borderBottomLeftRadius: 3,
            flexShrink: 0,
          }}
        />
        <span
          className="truncate flex-1"
          style={{
            fontSize: 10,
            fontWeight: 500,
            color: INK.textPrimary,
            padding: '0 4px',
          }}
        >
          {label}
        </span>
        <span
          className="shrink-0"
          style={{
            fontSize: 8.5,
            fontWeight: 700,
            color: s.color,
            letterSpacing: 0.5,
          }}
        >
          {s.tag}
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-1 !h-1 !bg-slate-300 !border-0 !-bottom-[2px]"
      />
    </>
  );
}

export default memo(PostTaskNodeComponent);
