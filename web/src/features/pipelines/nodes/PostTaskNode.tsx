import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { INK, NODE_SIZE, CARD_SHADOW, FONT_SANS } from './nodeTokens';

export type PostVariant = 'on_fail' | 'on_success' | 'always';

interface PostTaskNodeData {
  label: string;
  variant: PostVariant;
  parentTaskId: string;
  [key: string]: unknown;
}

// v5 (2026-08): 变体色对齐语义色板（on_fail 红、on_ok 绿、always slate）
const VARIANT_STYLE: Record<PostVariant, {
  color: string;
  tag: string;
}> = {
  on_fail: { color: '#EF4444', tag: 'ON_FAIL' },
  on_success: { color: '#10B981', tag: 'ON_OK' },
  always: { color: '#64748B', tag: 'ALWAYS' },
};

/**
 * Post 任务节点 —— v11 轻药丸
 *
 * v11 变化：左缘 3px 色条退役（craft-floor 禁 >1px 彩色 border-left），
 * 变体语义改由「色点 + 变体码」承载；handles 左入右出（LR）。
 * 尺寸/文案契约不变（POST_W 168 × POST_H 26，ON_FAIL/ON_OK/ALWAYS 标签）。
 */
function PostTaskNodeComponent({ data }: { data: PostTaskNodeData }) {
  const { label, variant } = data;
  const s = VARIANT_STYLE[variant];

  return (
    <>
      <Handle
        type="target"
        position={Position.Left}
        className="!w-1 !h-1 !bg-slate-300 !border-0 !-left-[2px]"
      />

      <div
        className="flex items-center bg-white select-none whitespace-nowrap"
        style={{
          width: NODE_SIZE.POST_W,
          height: NODE_SIZE.POST_H,
          padding: '0 8px 0 9px',
          gap: 6,
          border: `1px solid #E4E9F0`,
          borderRadius: 6,
          fontFamily: FONT_SANS,
          boxShadow: CARD_SHADOW,
        }}
      >
        {/* 变体色点（语义载体，替代旧左缘色条） */}
        <span
          aria-hidden
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            backgroundColor: s.color,
            flexShrink: 0,
          }}
        />
        <span
          className="truncate flex-1"
          style={{
            fontSize: 10.5,
            fontWeight: 500,
            color: INK.textPrimary,
          }}
        >
          {label}
        </span>
        <span
          className="shrink-0"
          style={{
            fontSize: 9,
            fontWeight: 600,
            color: INK.textSecondary,
            letterSpacing: 0.4,
          }}
        >
          {s.tag}
        </span>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="!w-1 !h-1 !bg-slate-300 !border-0 !-right-[2px]"
      />
    </>
  );
}

export default memo(PostTaskNodeComponent);
