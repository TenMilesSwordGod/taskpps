import { useMemo, useState, useId, type CSSProperties } from 'react';
import { Tooltip } from 'antd';

/** 单次运行的 task 汇总 */
interface RunSummary {
  task_summary: Record<string, number>;
}

interface SuccessRateChartProps {
  /** 最近 N 次运行（按时间倒序，最近在前） */
  runs: RunSummary[];
  /** 图表区域宽度，默认 150 */
  width?: number;
  /** 图表区域高度（不含底部统计），默认 36 */
  height?: number;
}

/** 计算单次运行的完成比
 * 完成比 = success / (total - skipped)
 * fail 不算通过，skip 不计入总数，分母为 0 时返回 0
 */
export function computeCompletionRatio(taskSummary: Record<string, number>): number {
  const success = taskSummary.success ?? 0;
  const skipped = taskSummary.skipped ?? 0;
  const total = Object.values(taskSummary).reduce((a, b) => a + b, 0);
  const denominator = total - skipped;
  return denominator > 0 ? success / denominator : 0;
}

/** 根据完成比返回数据点颜色 */
function getPointColor(ratio: number): string {
  if (ratio >= 1) return '#10b981';
  if (ratio > 0) return '#3D5BFF';
  return '#ef4444';
}

/** 根据平均完成比返回徽章颜色 */
function getAvgBadgeStyle(avg: number): CSSProperties {
  const pct = Math.round(avg * 100);
  if (pct >= 80) return { backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#10b981' };
  if (pct >= 50) return { backgroundColor: 'rgba(126, 173, 255, 0.12)', color: '#3D5BFF' };
  if (pct > 0) return { backgroundColor: 'rgba(239, 68, 68, 0.06)', color: '#ef4444' };
  return { backgroundColor: '#F6F6F8', color: '#7C7F88' };
}

/** 生成平滑曲线路径（Catmull-Rom → Bezier） */
function buildSmoothPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return '';
  if (pts.length === 1) return `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
  const d: string[] = [`M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;
    d.push(`C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`);
  }
  return d.join(' ');
}

/** 空状态 */
function EmptyState() {
  return <span style={{ color: '#7C7F88', fontSize: 12 }}>暂无运行</span>;
}

const containerStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
  cursor: 'pointer',
};

const statsRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  fontSize: 11,
  lineHeight: 1,
};

const badgeBaseStyle: CSSProperties = {
  padding: '1px 6px',
  borderRadius: 8,
  fontWeight: 600,
  fontSize: 11,
  lineHeight: '16px',
  whiteSpace: 'nowrap',
};

const passTextStyle: CSSProperties = {
  color: '#7C7F88',
  fontSize: 10,
};

/**
 * 成功率折线图组件
 *
 * 展示最近 N 次运行的 task 完成比趋势：
 * - 渐变区域填充 + 平滑曲线
 * - 悬停/点击数据点显示 Tooltip（第N次 + 完成比%）
 * - 数据点颜色编码（绿=100% 蓝=部分 红=0%）
 * - 底部 HTML 徽章显示平均完成比 + 全通过次数
 * - 支持 prefers-reduced-motion
 * - aria-label 无障碍标签
 */
export default function SuccessRateChart({
  runs,
  width = 150,
  height = 36,
}: SuccessRateChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const reactId = useId();
  const gradId = `src-grad-${reactId.replace(/:/g, '')}`;

  // runs 按时间倒序（最近在前），折线图左旧右新需反转
  const points = useMemo(
    () => [...runs].reverse().map((r) => computeCompletionRatio(r.task_summary ?? {})),
    [runs],
  );

  const stats = useMemo(() => {
    if (points.length === 0) return null;
    const avg = points.reduce((s, p) => s + p, 0) / points.length;
    const passCount = points.filter((p) => p >= 1).length;
    return { avg, passCount, total: points.length };
  }, [points]);

  if (points.length === 0) return <EmptyState />;

  const PAD_X = 5;
  const PAD_TOP = 4;
  const PAD_BOTTOM = 4;
  const plotW = width - PAD_X * 2;
  const plotH = height - PAD_TOP - PAD_BOTTOM;
  const stepX = points.length > 1 ? plotW / (points.length - 1) : 0;

  const coords = points.map((p, i) => ({
    x: PAD_X + i * stepX,
    y: PAD_TOP + (1 - p) * plotH,
    value: p,
    index: i,
  }));

  const smoothPath = buildSmoothPath(coords);
  const areaPath = `${smoothPath} L${coords[coords.length - 1].x.toFixed(1)},${(PAD_TOP + plotH).toFixed(1)} L${coords[0].x.toFixed(1)},${(PAD_TOP + plotH).toFixed(1)} Z`;

  const avgPct = Math.round(stats!.avg * 100);
  const tooltipText = hovered !== null
    ? `第 ${points.length - hovered} 次（共 ${stats!.total} 次）：完成比 ${Math.round(points[hovered] * 100)}%`
    : `最近 ${stats!.total} 次平均 ${avgPct}% · 全通过 ${stats!.passCount}/${stats!.total}`;
  const ariaLabel = `成功率折线图，最近${stats!.total}次运行，平均完成比${avgPct}%，全通过${stats!.passCount}次`;

  return (
    <Tooltip title={tooltipText} placement="top">
      <div style={containerStyle} aria-label={ariaLabel} role="img">
        <svg
          width={width}
          height={height}
          style={{ display: 'block' }}
          onMouseLeave={() => setHovered(null)}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3D5BFF" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#3D5BFF" stopOpacity={0.02} />
            </linearGradient>
          </defs>

          {/* 区域填充 */}
          <path d={areaPath} fill={`url(#${gradId})`} />
          {/* 平滑折线 */}
          <path
            d={smoothPath}
            fill="none"
            stroke="#3D5BFF"
            strokeWidth={1.8}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* 悬停辅助竖线 */}
          {hovered !== null && (
            <line
              x1={coords[hovered].x} y1={PAD_TOP}
              x2={coords[hovered].x} y2={PAD_TOP + plotH}
              stroke="#3D5BFF" strokeWidth={1} strokeDasharray="2 2" strokeOpacity={0.35}
            />
          )}

          {/* 数据点 + 透明热区（便于悬停/触摸） */}
          {coords.map((c) => (
            <g key={c.index}>
              {/* 透明热区，扩大触摸范围 */}
              <circle
                cx={c.x}
                cy={c.y}
                r={8}
                fill="transparent"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHovered(c.index)}
                onClick={() => setHovered(c.index)}
              />
              <circle
                cx={c.x}
                cy={c.y}
                r={hovered === c.index ? 3.5 : 2.5}
                fill={getPointColor(c.value)}
                stroke="#fff"
                strokeWidth={1.2}
                style={{ transition: 'r 120ms ease-out', pointerEvents: 'none' }}
              />
            </g>
          ))}
        </svg>

        {/* 底部统计徽章 */}
        <div style={statsRowStyle}>
          <span style={{ ...badgeBaseStyle, ...getAvgBadgeStyle(stats!.avg) }}>
            {avgPct}%
          </span>
          <span style={passTextStyle}>
            {stats!.passCount}/{stats!.total} pass
          </span>
        </div>
      </div>
    </Tooltip>
  );
}
