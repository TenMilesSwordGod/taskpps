import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { CirclePlay, Square } from 'lucide-react';

interface StartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

function StartEndNodeComponent({ data }: { data: StartEndNodeData }) {
  const isStart = data.variant === 'start';

  return (
    <>
      {!isStart && <Handle type="target" position={Position.Top} className="!w-2 !h-2 !bg-gray-400" />}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 14px',
          background: '#ffffff',
          border: `2px solid ${isStart ? '#22c55e' : '#d1d5db'}`,
          borderRadius: 8,
          fontSize: 12,
          fontWeight: 500,
          color: isStart ? '#16a34a' : '#6b7280',
          boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
          userSelect: 'none',
          whiteSpace: 'nowrap',
        }}
      >
        {isStart ? <CirclePlay size={14} /> : <Square size={12} />}
        {isStart ? 'Start' : 'End'}
      </div>

      {isStart && <Handle type="source" position={Position.Bottom} className="!w-2 !h-2 !bg-gray-400" />}
    </>
  );
}

export const StartNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
export const EndNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
