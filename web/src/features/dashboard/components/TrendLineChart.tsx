import { useEffect, useLayoutEffect, useId, useMemo, useRef, useState } from 'react';

interface TrendPoint {
  label: string;
  value: number;
  /** 单次运行的状态（用于 tooltip 显示“跑的情况”） */
  status?: string;
  statusColor?: string;
  /** 运行时间（用于 tooltip） */
  time?: string;
  /** 关联的运行 ID，存在时 tooltip / 数据点可点击跳转 */
  id?: string;
  /** tooltip 中的补充描述，例如每日聚合时列出“共 N 次执行: X, Y” */
  detail?: string;
}

interface TrendLineChartProps {
  data: TrendPoint[];
  height?: number;
  color?: string;
  /** tooltip 数值单位，如 "次" / "秒" */
  unit?: string;
  /** 点击某个数据点（需该点带 id）时的回调，用于跳转运行详情 */
  onPointClick?: (id: string) => void;
}

/**
 * 生成平滑曲线路径（Catmull-Rom → Bezier）
 * 控制点的 y 坐标会被 clamp 到 [yMin, yMax] 之间。由于三次贝塞尔曲线位于
 * 其四个控制点构成的凸包内，clamp 后曲线不会越过绘图区上下边界，
 * 避免“连续两个 0% 之间被 Catmull-Rom 推到负值”的过冲。
 */
function buildSmoothPath(
  pts: { x: number; y: number }[],
  yMin = -Infinity,
  yMax = Infinity,
): string {
  if (pts.length === 0) return '';
  if (pts.length === 1) return `M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
  const d: string[] = [`M${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`];
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = clamp(p1.y + (p2.y - p0.y) / 6, yMin, yMax);
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = clamp(p2.y - (p3.y - p1.y) / 6, yMin, yMax);
    d.push(`C${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`);
  }
  return d.join(' ');
}

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/**
 * 趋势折线图（按容器真实宽高自适应渲染，铺满父容器，避免拉伸）。
 * 支持鼠标悬停：跟随光标的竖线 + 高亮点 + tooltip（显示名称、数值，以及运行状态/时间）。
 */
export default function TrendLineChart({ data, height = 220, color = '#3D5BFF', unit = '', onPointClick }: TrendLineChartProps) {
  const reactId = useId();
  const gradId = `trend-grad-${reactId.replace(/:/g, '')}`;
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const lineRef = useRef<SVGPathElement>(null);
  // 同时测量容器宽高，避免只自适应宽度导致高度写死出现大片留白
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 600, h: height });
  const [hover, setHover] = useState<number | null>(null);
  const [showMarks, setShowMarks] = useState(false);

  // 仅当数据本身变化时触发绘制动画（resize 改变宽度不重播）
  const dataSignature = useMemo(
    () => data.map((d) => `${d.label}:${d.value}`).join('|'),
    [data],
  );

  // 折线“绘制”动画：用 stroke-dashoffset 从路径长度收到 0；区域/数据点随后淡入
  // 依赖 dataSignature + size.w：宽度变化（如首次 ResizeObserver 上报真实宽度、
  // 或窗口/布局 resize）后必须基于“最新 path 实际长度”重设 dash 并重播，
  // 否则旧 dash 长度与新 path 失配 → 右侧留白 / 绘制方向异常（issue #193）。
  useEffect(() => {
    const path = lineRef.current;
    if (!path) return;
    const len = path.getTotalLength();
    path.style.transition = 'none';
    path.style.strokeDasharray = `${len}`;
    path.style.strokeDashoffset = `${len}`;
    path.getBoundingClientRect(); // 强制重排，确保起始态生效
    path.style.transition = 'stroke-dashoffset 0.9s ease';
    path.style.strokeDashoffset = '0';

    setShowMarks(false);
    const t1 = window.setTimeout(() => setShowMarks(true), 320);
    // 动画结束后清除 dash，避免之后 resize 导致路径变长出现缺口
    const t2 = window.setTimeout(() => {
      path.style.transition = 'none';
      path.style.strokeDasharray = 'none';
      path.style.strokeDashoffset = '0';
    }, 950);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [dataSignature, size.w]);

  // 挂载即用真实尺寸测量一次，避免初始默认值的闪烁/错位。
  // 首帧布局未就绪时 getBoundingClientRect 可能返回 0（父级 flex 尚未完成），
  // 此时不回退到默认 600 半宽，而是用 rAF 在下一帧再测一次拿真实宽度，
  // 配合上面 size.w 依赖的绘制动画，确保折线铺满真实容器宽度（issue #193）。
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 || rect.height > 0) {
        setSize((prev) => ({
          w: rect.width > 0 ? rect.width : prev.w,
          h: rect.height > 0 ? rect.height : prev.h,
        }));
      }
    };
    measure();
    const raf = requestAnimationFrame(measure);
    return () => cancelAnimationFrame(raf);
  }, []);

  // 容器尺寸变化时同步宽高，真正自适应铺满（含高度）
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      const w = cr?.width ?? el.getBoundingClientRect().width;
      const h = cr?.height ?? el.getBoundingClientRect().height;
      setSize((prev) => ({
        w: w > 0 ? w : prev.w,
        h: h > 0 ? h : prev.h,
      }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // v2 (2026-07): 空数据不再 early-return 一个「无 containerRef 的占位 div」。
  // 之前写法在首次挂载 data 为空（仪表盘 useRuns 异步、首挂 trendData 为空）时，
  // 渲染的占位 div 没有 containerRef → 测量用的 useLayoutEffect / ResizeObserver
  // 读到 containerRef.current===null 直接 return，且 deps=[] 不随数据到达重跑 →
  // size.w 恒为默认 600 → 折线只画半宽（issue #193, zentao bug #31）。
  // 改为：始终渲染带 ref 的最外层容器，「暂无数据」作为容器内的内联内容，
  // 保证挂载时 containerRef 必然存在、测量 effect 必能拿到真实宽度。
  const isEmpty = !data || data.length === 0;

  // 实际渲染所用宽高：优先取容器实测值，回退到 props（避免初次 0）
  const width = size.w > 0 ? size.w : 600;
  const chartH = size.h > 0 ? size.h : height;

  const PAD_L = 12;
  const PAD_R = 12;
  const PAD_T = 16;
  const PAD_B = 30;
  const plotW = width - PAD_L - PAD_R;
  const plotH = chartH - PAD_T - PAD_B;
  const maxVal = Math.max(1, ...data.map((d) => d.value));
  const n = data.length;
  const stepX = n > 1 ? plotW / (n - 1) : 0;

  const coords = data.map((d, i) => ({
    x: PAD_L + i * stepX,
    y: PAD_T + (1 - d.value / maxVal) * plotH,
    value: d.value,
    label: d.label,
    status: d.status,
    statusColor: d.statusColor,
    time: d.time,
    id: d.id,
    detail: d.detail,
  }));

  // 绘图区上下边界（像素坐标），用于 clamp 平滑曲线控制点，杜绝过冲
  const yTop = PAD_T;
  const yBottom = PAD_T + plotH;
  const smoothPath = buildSmoothPath(coords, yTop, yBottom);
  // v2 (2026-07): 空数据时 coords 为空，coords[n-1] 会越界；仅在有数据时构造区域路径
  const areaPath = n > 0
    ? `${smoothPath} L${coords[n - 1].x.toFixed(1)},${yBottom.toFixed(1)} L${coords[0].x.toFixed(1)},${yBottom.toFixed(1)} Z`
    : '';
  const labelStep = Math.max(1, Math.ceil(n / 6));

  const handleMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg || n === 0) return;
    const rect = svg.getBoundingClientRect();
    const x = e.clientX - rect.left;
    let nearest = 0;
    let best = Infinity;
    for (let i = 0; i < n; i++) {
      const diff = Math.abs(coords[i].x - x);
      if (diff < best) {
        best = diff;
        nearest = i;
      }
    }
    setHover(nearest);
  };

  const active = hover != null ? coords[hover] : null;
  const tipAbove = active ? active.y > 56 : true;
  const tipLeft = active ? clamp(active.x, 56, width - 56) : 0;
  const tipTop = active ? (tipAbove ? active.y - 10 : active.y + 10) : 0;
  const clickable = !!active?.id && !!onPointClick;

  const handleClick = () => {
    if (active?.id && onPointClick) onPointClick(active.id);
  };

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', position: 'relative' }}>
      {/* v2 (2026-07): 「暂无数据」内联在带 ref 的容器内，容器本身始终挂载，测量 effect 恒生效 */}
      {isEmpty && (
        <div style={{ height: '100%', minHeight: height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#7C7F88', fontSize: 12 }}>
          暂无数据
        </div>
      )}
      {!isEmpty && (
      <>
      <svg
        ref={svgRef}
        width="100%"
        height={chartH}
        style={{ display: 'block', cursor: clickable ? 'pointer' : hover != null ? 'crosshair' : 'default' }}
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
        onClick={handleClick}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        {/* 基线 */}
        <line x1={PAD_L} y1={PAD_T + plotH} x2={width - PAD_R} y2={PAD_T + plotH} stroke="#E3E4E8" strokeWidth={1} />

        {/* 区域填充 + 平滑曲线 */}
        <path
          d={areaPath}
          fill={`url(#${gradId})`}
          style={{ opacity: showMarks ? 1 : 0, transition: 'opacity 0.6s ease 0.25s' }}
        />
        <path
          ref={lineRef}
          d={smoothPath}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* 悬停竖线 + 高亮点 */}
        {active && (
          <g>
            <line x1={active.x} y1={PAD_T} x2={active.x} y2={PAD_T + plotH} stroke={color} strokeWidth={1} strokeDasharray="3 3" opacity={0.6} />
            <circle cx={active.x} cy={active.y} r={4.5} fill={color} stroke="#fff" strokeWidth={2} />
          </g>
        )}

        {/* 数据点 + x 轴标签 */}
        {coords.map((c, i) => {
          const showLabel = i % labelStep === 0;
          const labelX = clamp(c.x, PAD_L + 26, width - PAD_R - 26);
          return (
            <g key={i}>
              <g style={{ opacity: showMarks ? 1 : 0, transition: 'opacity 0.4s ease 0.4s' }}>
                <circle cx={c.x} cy={c.y} r={c.value > 0 ? 2.5 : 1.5} fill={c.value > 0 ? color : '#C9CBD3'} stroke="#fff" strokeWidth={1.2} />
              </g>
              {showLabel && (
                <text x={labelX} y={PAD_T + plotH + 16} fontSize={10} fill="#7C7F88" textAnchor="middle">
                  {c.label}
                </text>
              )}
            </g>
          );
        })}

        {/* y 轴峰值标注 */}
        <text x={PAD_L} y={PAD_T - 4} fontSize={10} fill="#7C7F88">
          {maxVal}
          {unit}
        </text>
      </svg>

      {/* tooltip：名称 + 运行状态/时间 + 数值 */}
      {active && (
        <div
          style={{
            position: 'absolute',
            left: tipLeft,
            top: tipTop,
            transform: `translate(-50%, ${tipAbove ? '-100%' : '0'})`,
            background: '#121620',
            color: '#fff',
            padding: '6px 10px',
            borderRadius: 6,
            fontSize: 11,
            lineHeight: 1.5,
            whiteSpace: 'nowrap',
            pointerEvents: 'none',
            boxShadow: '0 4px 12px rgba(1, 24, 33, 0.25)',
            zIndex: 2,
          }}
        >
          <div style={{ opacity: 0.7, fontSize: 10 }}>{active.label}</div>
          {active.status && (
            <div style={{ fontWeight: 600, color: active.statusColor ?? '#fff' }}>状态：{active.status}</div>
          )}
          <div style={{ fontWeight: 600 }}>
            {active.value}
            {unit && <span style={{ opacity: 0.7, fontWeight: 400 }}> {unit}</span>}
          </div>
          {active.time && <div style={{ opacity: 0.7, fontSize: 10 }}>{active.time}</div>}
          {active.detail && <div style={{ opacity: 0.6, fontSize: 10, marginTop: 1 }}>{active.detail}</div>}
          {clickable && <div style={{ opacity: 0.6, fontSize: 10, marginTop: 2 }}>点击查看详情 →</div>}
        </div>
      )}
      </>
      )}
    </div>
  );
}
