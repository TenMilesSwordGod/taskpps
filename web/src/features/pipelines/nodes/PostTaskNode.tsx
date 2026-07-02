import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { AlertCircle, CheckCircle, RotateCcw } from 'lucide-react';

export type PostVariant = 'on_fail' | 'on_success' | 'always';

interface PostTaskNodeData {
  label: string;
  variant: PostVariant;
  parentTaskId: string;
  [key: string]: unknown;
}

const VARIANT_STYLES: Record<PostVariant, {
  bg: string;
  border: string;
  color: string;
  icon: React.ReactNode;
  tag: string;
}> = {
  on_fail: {
    bg: '#fff7ed',
    border: '#f97316',
    color: '#ea580c',
    icon: <AlertCircle size={14} />,
    tag: '失败时',
  },
  on_success: {
    bg: '#f0fdf4',
    border: '#22c55e',
    color: '#16a34a',
    icon: <CheckCircle size={14} />,
    tag: '成功时',
  },
  always: {
    bg: '#f9fafb',
    border: '#9ca3af',
    color: '#6b7280',
    icon: <RotateCcw size={14} />,
    tag: '始终',
  },
};

function PostTaskNodeComponent({ data }: { data: PostTaskNodeData }) {
  const { label, variant } = data;
  const s = VARIANT_STYLES[variant];

  return (
    <>
      <Handle type="target" position={Position.Top} className="!w-2 !h-2 !bg-gray-400" />

      <div
        style={{
          width: 160,
          padding: '4px 8px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          background: s.bg,
          border: `1.5px dashed ${s.border}`,
          borderRadius: 8,
          color: s.color,
          fontSize: 11,
          cursor: 'default',
          userSelect: 'none',
        }}
      >
        {s.icon}
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {label}
        </span>
        <span style={{
          fontSize: 9,
          padding: '0 4px',
          borderRadius: 4,
          background: s.border,
          color: '#fff',
          whiteSpace: 'nowrap',
        }}>
          {s.tag}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!w-2 !h-2 !bg-gray-400" />
    </>
  );
}

export default memo(PostTaskNodeComponent);
