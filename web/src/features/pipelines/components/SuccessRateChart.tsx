import { useMemo, useState, useId, type CSSProperties } from 'react';
import { Tooltip } from 'antd';

/** 单次运行的 task 汇总 */
interface RunSummary {
  task_summary: Record<string, number>;
}

interface SuccessRateChartProps {
  /** 最近 N 次运行（按时间倒序，最近在前） */
  runs: RunSummary[];
  /** 图表宽度，默认 150 */
  width?: number;
  /** 图表高度，默认 44 */
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
  if (ratio >= 1) return '#16a34a';
  if (ratio > 0) return '#3b82f6';
  return '#ef4444';
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
  return <span style={{ color: '#9ca3af', fontSize: 12 }}>暂无运行</span>;
}

/**
 * 成功率折线图组件
 *
 * 展示最近 N 次运行的 task 完成比趋势：
 * - 渐变区域填充 + 平滑曲线
 * - 100% / 50% 参考线
 * - 悬停数据点显示 Tooltip（第N次 + 完成比%）
 * - 数据点颜色编码（绿=100% 蓝=部分 红=0%）
 * - 底部显示最近 N 次平均完成比
 */
export default function SuccessRateChart({
  runs,
  width = 150,
  height = 44,
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

  const PAD_X = 6;
  const PAD_TOP = 6;
  const PAD_BOTTOM = 12; // 底部留白给平均文字
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

  const tooltipText = hovered !== null
    ? `第 ${points.length - hovered} 次（共 ${stats!.total} 次）：完成比 ${Math.round(points[hovered] * 100)}%`
    : undefined;
  const defaultTooltip = `最近 ${stats!.total} 次平均 ${Math.round(stats!.avg * 100)}% · 全通过 ${stats!.passCount}/${stats!.total}`;

  const svgStyle: CSSProperties = { display: 'block', cursor: 'pointer' };
  const labelStyle: CSSProperties = { fontSize: 9, fill: '#9ca3af', fontFamily: 'sans-serif' };

  return (
    <Tooltip title={tooltipText ?? defaultTooltip} placement="top">
      <svg
        width={width}
        height={height}
        style={svgStyle}
        onMouseLeave={() => setHovered(null)}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* 100% 参考线 */}
        <line
          x1={PAD_X} y1={PAD_TOP} x2={width - PAD_X} y2={PAD_TOP}
          stroke="#e5e7eb" strokeWidth={1} strokeDasharray="3 2"
        />
        {/* 50% 参考线 */}
        <line
          x1={PAD_X} y1={PAD_TOP + plotH * 0.5} x2={width - PAD_X} y2={PAD_TOP + plotH * 0.5}
          stroke="#f3f4f6" strokeWidth={1} strokeDasharray="2 3"
        />
        {/* Y 轴标签 */}
        <text x={PAD_X} y={PAD_TOP - 1} style={labelStyle} textAnchor="start">100%</text>

        {/* 区域填充 */}
        <path d={areaPath} fill={`url(#${gradId})`} />
        {/* 平滑折线 */}
        <path
          d={smoothPath}
          fill="none"
          stroke="#3b82f6"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* 悬停辅助竖线 */}
        {hovered !== null && (
          <line
            x1={coords[hovered].x} y1={PAD_TOP}
            x2={coords[hovered].x} y2={PAD_TOP + plotH}
            stroke="#3b82f6" strokeWidth={1} strokeDasharray="2 2" strokeOpacity={0.4}
          />
        )}

        {/* 数据点 */}
        {coords.map((c) => (
          <circle
            key={c.index}
            cx={c.x}
            cy={c.y}
            r={hovered === c.index ? 3.5 : 2.2}
            fill={getPointColor(c.value)}
            stroke="#fff"
            strokeWidth={1.2}
            style={{ cursor: 'pointer', transition: 'r 120ms ease-out' }}
            onMouseEnter={() => setHovered(c.index)}
          />
        ))}

        {/* 底部平均完成比文字 */}
        <text
          x={width / 2}
          y={height - 2}
          style={labelStyle}
          textAnchor="middle"
        >
          avg {Math.round(stats!.avg * 100)}%
        </text>
      </svg>
    </Tooltip>
  );
}
