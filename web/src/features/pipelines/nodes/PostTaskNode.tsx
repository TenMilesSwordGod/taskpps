import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react';

export type PostVariant = 'on_fail' | 'on_success' | 'always';

interface PostTaskNodeData {
  label: string;
  variant: PostVariant;
  parentTaskId: string;
  [key: string]: unknown;
}

const VARIANT_STYLE: Record<PostVariant, {
  border: string;
  color: string;
  icon: React.ReactNode;
  tag: string;
}> = {
  on_fail: {
    border: '#f97316',
    color: '#ea580c',
    icon: <AlertTriangle size={12} />,
    tag: 'on_fail',
  },
  on_success: {
    border: '#22c55e',
    color: '#16a34a',
    icon: <CheckCircle2 size={12} />,
    tag: 'on_success',
  },
  always: {
    border: '#a3a3a3',
    color: '#737373',
    icon: <RefreshCw size={12} />,
    tag: 'always',
  },
};

function PostTaskNodeComponent({ data }: { data: PostTaskNodeData }) {
  const { label, variant } = data;
  const s = VARIANT_STYLE[variant];

  return (
    <>
      <Handle type="target" position={Position.Top} className="!w-1.5 !h-1.5" />

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          padding: '3px 10px',
          background: '#ffffff',
          border: `1.5px solid ${s.border}`,
          borderLeftWidth: 3,
          borderRadius: 6,
          fontSize: 11,
          color: '#374151',
          boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
          userSelect: 'none',
          whiteSpace: 'nowrap',
          maxWidth: 160,
        }}
      >
        <span style={{ color: s.color, flexShrink: 0, display: 'flex' }}>{s.icon}</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
        <span
          style={{
            fontSize: 9,
            color: s.color,
            background: `${s.border}14`,
            padding: '0 4px',
            borderRadius: 3,
            fontWeight: 500,
            flexShrink: 0,
          }}
        >
          {s.tag}
        </span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!w-1.5 !h-1.5" />
    </>
  );
}

export default memo(PostTaskNodeComponent);
