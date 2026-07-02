import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';

interface StartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

function StartEndNodeComponent({ data }: { data: StartEndNodeData }) {
  const isStart = data.variant === 'start';

  return (
    <>
      {!isStart && <Handle type="target" position={Position.Top} className="!w-1.5 !h-1.5" />}

      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 10px',
        fontSize: 11,
        fontWeight: 500,
        color: '#6b7280',
        userSelect: 'none',
      }}>
        <span style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: isStart ? '#22c55e' : '#9ca3af',
          flexShrink: 0,
        }} />
        {isStart ? 'Start' : 'End'}
      </div>

      {isStart && <Handle type="source" position={Position.Bottom} className="!w-1.5 !h-1.5" />}
    </>
  );
}

export const StartNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
export const EndNode = memo((props: { data: StartEndNodeData }) => (
  <StartEndNodeComponent {...props} />
));
