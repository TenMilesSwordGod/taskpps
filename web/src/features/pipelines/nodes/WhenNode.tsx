import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Tooltip } from 'antd';

interface WhenTargetInfo {
  targetId: string;
  when: string;
}

interface WhenNodeData {
  isGateway?: boolean;
  when?: string;
  whenTargets?: WhenTargetInfo[];
  sourceTaskName?: string;
  targetTaskName?: string;
}

const MAX_SUMMARY_LEN = 10;
const GATEWAY_SIZE = 50;

function summarizeWhen(when: string): string {
  const match = when.match(/\$\{([^}]+)\}/);
  if (match) return `\${${match[1]}}`;
  return when.length > MAX_SUMMARY_LEN ? `${when.slice(0, MAX_SUMMARY_LEN)}…` : when;
}

function GatewayNode() {
  return (
    <div
      data-testid="gateway-node"
      className="relative w-[50px] h-[50px] flex items-center justify-center"
      title="Gateway"
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-amber-500"
      />

      <svg
        className="absolute inset-0 w-full h-full"
        viewBox={`0 0 ${GATEWAY_SIZE} ${GATEWAY_SIZE}`}
        style={{ filter: 'drop-shadow(0 2px 6px rgba(245, 158, 11, 0.25))' }}
      >
        <polygon
          points="25,2 48,25 25,48 2,25"
          fill="#F59E0B"
          stroke="#D97706"
          strokeWidth="2"
        />
        <line x1="12" y1="12" x2="38" y2="38" stroke="white" strokeWidth="2" />
        <line x1="38" y1="12" x2="12" y2="38" stroke="white" strokeWidth="2" />
      </svg>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-amber-500"
      />
    </div>
  );
}

function WhenNodeComponent(props: NodeProps) {
  const { isGateway, when, sourceTaskName, targetTaskName } = (props.data ?? {}) as unknown as WhenNodeData;

  if (isGateway) {
    return <GatewayNode />;
  }

  const summary = when ? summarizeWhen(when) : '';

  return (
    <div
      data-testid="when-node"
      className="relative w-[90px] h-[90px] flex items-center justify-center"
      title={`${sourceTaskName ?? ''} → ${targetTaskName ?? ''}`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!w-2 !h-2 !bg-amber-500"
      />

      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 90 90"
        style={{ filter: 'drop-shadow(0 4px 12px rgba(245, 158, 11, 0.25))' }}
      >
        <polygon
          points="45,2 88,45 45,88 2,45"
          fill="#F59E0B"
          stroke="#D97706"
          strokeWidth="2"
        />
      </svg>

      <Tooltip title={when}>
        <span
          data-testid="when-node-text"
          className="relative z-10 text-white text-xs font-mono font-medium truncate max-w-[60px] text-center leading-tight cursor-default select-none"
        >
          {summary}
        </span>
      </Tooltip>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-2 !h-2 !bg-amber-500"
      />
    </div>
  );
}

export default memo(WhenNodeComponent);
