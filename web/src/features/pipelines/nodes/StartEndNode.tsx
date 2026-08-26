import { memo } from 'react';
import { Handle, Position } from '@xyflow/react';
import { NODE_SIZE, INK, TYPE_ICON_BG, SENTINEL_ICON, FONT_SANS } from './nodeTokens';

interface StartEndNodeData {
  variant: 'start' | 'end';
  [key: string]: unknown;
}

/**
 * Start / End 哨兵节点 —— v11 trigger 式节点卡片
 *
 * 为什么改（v7 圆形 → v11 卡片）：通用流程图的圆形▶/■哨兵是"AI 生成感"
 * 的来源之一；n8n 的画布上没有圆形哨兵 —— 触发器就是一张节点卡片。
 * START = emerald 图标块 + "开始 / Trigger"；END = slate 图标块 + "结束 / End"。
 * 尺寸与任务卡同高（56px），视觉节奏统一。
 *
 * 保留的既有结论：START 绿色系（入口语义）、END slate（终点语义），
 * 形状一致仅色相区分（v6 无障碍结论）。
 */
function StartEndNodeComponent({ data }: { data: StartEndNodeData }) {
  const isStart = data.variant === 'start';
  const w = isStart ? NODE_SIZE.SENTINEL_START_W : NODE_SIZE.SENTINEL_END_W;
  const h = NODE_SIZE.SENTINEL_H;
  const Glyph = isStart ? SENTINEL_ICON.start : SENTINEL_ICON.end;
  // v11.1: START/END 图标块统一石墨（用户反馈绿色丑；入口语义由绿色出边承载）
  const blockBg = TYPE_ICON_BG;
  const label = isStart ? '开始' : '结束';
  const sub = isStart ? 'Trigger' : 'End';

  return (
    <>
      {!isStart && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-left-[3px]"
        />
      )}

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
          boxShadow: '0 1px 2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.07)',
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
      </div>

      {isStart && (
        <Handle
          type="source"
          position={Position.Right}
          className="!w-1.5 !h-1.5 !bg-slate-300 !border-0 !-right-[3px]"
        />
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
