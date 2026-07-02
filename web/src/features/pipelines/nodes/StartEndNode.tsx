import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Play, Square } from 'lucide-react';

interface StartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

const STYLES = {
  start: {
    bg: '#f0fdf4',
    border: '#22c55e',
    color: '#16a34a',
    icon: <Play size={14} fill="currentColor" />,
    label: 'Start',
  },
  end: {
    bg: '#fef2f2',
    border: '#ef4444',
    color: '#dc2626',
    icon: <Square size={14} fill="currentColor" />,
    label: 'End',
  },
} as const;

function StartEndNodeComponent({ data }: { data: StartEndNodeData }) {
  const { variant } = data;
  const s = STYLES[variant];

  return (
    <>
      {variant === 'end' && (
        <Handle type="target" position={Position.Top} className="!w-2 !h-2 !bg-gray-400" />
      )}

      <div
        style={{
          width: 80,
          height: 36,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 4,
          background: s.bg,
          border: `2px solid ${s.border}`,
          borderRadius: 18,
          color: s.color,
          fontSize: 12,
          fontWeight: 600,
          cursor: 'default',
          userSelect: 'none',
        }}
      >
        {s.icon}
        {s.label}
      </div>

      {variant === 'start' && (
        <Handle type="source" position={Position.Bottom} className="!w-2 !h-2 !bg-gray-400" />
      )}
    </>
  );
}

export const StartNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
export const EndNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
