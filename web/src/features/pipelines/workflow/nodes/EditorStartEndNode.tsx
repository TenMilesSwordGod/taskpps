import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import {
  NODE_SIZE,
  INK,
  SENTINEL_ICON,
  FONT_SANS,
  CARD_SHADOW,
} from '@/features/pipelines/nodes/nodeTokens';
import { useReadOnly } from './ReadOnlyContext';

interface EditorStartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

/**
 * Start / End 哨兵节点 —— v11 (2026-08) trigger 式卡片，与查看模式 StartEndNode 统一
 *
 * 为什么改：圆形哨兵是通用流程图语汇（"AI 生成感"来源）；n8n 的触发器
 * 是节点卡片。START = emerald 图标块 + 开始/Trigger；END = slate + 结束/End。
 * handle 随 LR 流向迁移：START out=Right、END in=Left。
 * 保留 handle id 契约（out/in）→ 边数据与 isValidConnection 零改动。
 */
function EditorStartEndNode({ data, selected }: { data: EditorStartEndNodeData; selected?: boolean }) {
  const readOnly = useReadOnly();
  const isStart = data.variant === 'start';
  const w = isStart ? NODE_SIZE.SENTINEL_START_W : NODE_SIZE.SENTINEL_END_W;
  const h = NODE_SIZE.SENTINEL_H;
  const Glyph = isStart ? SENTINEL_ICON.start : SENTINEL_ICON.end;
  // v11.1: START/END 图标块统一石墨（与查看模式 StartEndNode 一致）
  const blockBg = '#343A43';
  const label = isStart ? '开始' : '结束';
  const sub = isStart ? 'Trigger' : 'End';

  return (
    <div
      style={{
        width: w,
        height: h,
        borderRadius: 10,
        backgroundColor: INK.card,
        border: `1.5px solid ${INK.border}`,
        display: 'flex',
        alignItems: 'center',
        gap: 9,
        padding: '0 12px 0 10px',
        boxShadow: selected && !readOnly
          ? `0 0 0 2px ${INK.accent}55, ${CARD_SHADOW}`
          : CARD_SHADOW,
        boxSizing: 'border-box',
      }}
    >
      <div
        aria-hidden
        style={{
          width: 36,
          height: 36,
          borderRadius: 8,
          backgroundColor: blockBg,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <Glyph style={{ fontSize: 16, color: '#FFFFFF' }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <span
          style={{
            fontFamily: FONT_SANS,
            fontSize: 13,
            fontWeight: 600,
            color: INK.textPrimary,
            lineHeight: 1.25,
            whiteSpace: 'nowrap',
          }}
        >
          {label}
        </span>
        <span
          style={{
            fontFamily: FONT_SANS,
            fontSize: 10.5,
            color: INK.textSecondary,
            lineHeight: 1.2,
            whiteSpace: 'nowrap',
          }}
        >
          {sub}
        </span>
      </div>

      {!readOnly && (isStart ? (
        <Handle
          id="out"
          type="source"
          position={Position.Right}
          style={{
            width: 10,
            height: 10,
            background: '#FFFFFF',
            border: '2px solid #64748b',
            borderRadius: '50%',
            right: -6,
            top: '50%',
          }}
        />
      ) : (
        <Handle
          id="in"
          type="target"
          position={Position.Left}
          style={{
            width: 10,
            height: 10,
            background: '#FFFFFF',
            border: '2px solid #64748b',
            borderRadius: '50%',
            left: -6,
            top: '50%',
          }}
        />
      ))}
    </div>
  );
}

export default memo(EditorStartEndNode);
