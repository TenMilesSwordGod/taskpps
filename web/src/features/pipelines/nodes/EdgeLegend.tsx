import { useState } from 'react';
import { CaretRightOutlined } from '@ant-design/icons';
import { EDGE, FONT_SANS } from './nodeTokens';

/**
 * v6 (2026-08): 边线型图例 —— 画布四种边线语义此前零解释全靠记忆，
 * 违背「识别优先于回忆」。可折叠设计避免常驻占用画布空间。
 *
 * v11 (2026-08): 随视觉世界替换同步 —— 虚线全部退役（n8n 画布无虚线），
 * 语义靠色相/明度区分；样式从 mono 芯片改为 sans 弱文本，
 * 线样与实际连线同源（引用 nodeTokens.EDGE，换肤自动跟随）。
 */

const LEGEND_ITEMS: Array<{ color: string; width?: number; label: string }> = [
  { color: EDGE.start.stroke, label: '入口 / 条件成立' },
  { color: EDGE.rail.stroke, label: '主流程' },
  { color: EDGE.cross.stroke, label: '跨组依赖' },
  { color: EDGE.railSoft.stroke, width: 1.75, label: '条件跳过' },
];

/** 可折叠边线型图例（默认展开） */
export default function EdgeLegend() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      data-testid="edge-legend"
      data-collapsed={collapsed ? 'true' : 'false'}
      style={{
        background: 'rgba(255, 255, 255, 0.92)',
        border: '1px solid #E4E9F0',
        borderRadius: 8,
        boxShadow: '0 1px 3px rgba(15, 23, 42, 0.06)',
        padding: collapsed ? '4px 8px' : '6px 10px',
        fontFamily: FONT_SANS,
        fontSize: 11,
        pointerEvents: 'auto',
      }}
    >
      <button
        data-testid="edge-legend-toggle"
        onClick={() => setCollapsed((c) => !c)}
        aria-label={collapsed ? '展开图例' : '收起图例'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 5,
          border: 'none',
          background: 'transparent',
          cursor: 'pointer',
          font: 'inherit',
          fontWeight: 600,
          color: '#64748B',
          width: '100%',
          padding: 0,
        }}
      >
        <CaretRightOutlined
          style={{ fontSize: 9, transform: collapsed ? 'rotate(0deg)' : 'rotate(90deg)', transition: 'transform 0.15s' }}
        />
        <span>图例</span>
      </button>

      {!collapsed && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 6 }}>
          {LEGEND_ITEMS.map((item) => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <svg width="22" height="8" aria-hidden>
                <line
                  x1="0"
                  y1="4"
                  x2="22"
                  y2="4"
                  stroke={item.color}
                  strokeWidth={item.width ?? 1.8}
                  strokeLinecap="round"
                />
              </svg>
              <span style={{ color: '#64748B' }}>{item.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
