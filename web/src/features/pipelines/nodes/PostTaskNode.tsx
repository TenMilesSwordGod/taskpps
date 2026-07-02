import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

export type PostVariant = 'on_fail' | 'on_success' | 'always';

interface PostTaskNodeData {
  label: string;
  variant: PostVariant;
  parentTaskId: string;
  [key: string]: unknown;
}

const VARIANT_DOT: Record<PostVariant, string> = {
  on_fail: '#f97316',
  on_success: '#22c55e',
  always: '#9ca3af',
};

function PostTaskNodeComponent({ data }: { data: PostTaskNodeData }) {
  const { label, variant } = data;
  const dotColor = VARIANT_DOT[variant];

  return (
    <>
      <Handle type="target" position={Position.Top} className="!w-1.5 !h-1.5" />

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '2px 8px',
        fontSize: 11,
        color: '#6b7280',
        userSelect: 'none',
        whiteSpace: 'nowrap',
      }}>
        <span style={{
          width: 5,
          height: 5,
          borderRadius: '50%',
          background: dotColor,
          flexShrink: 0,
        }} />
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!w-1.5 !h-1.5" />
    </>
  );
}

export default memo(PostTaskNodeComponent);
