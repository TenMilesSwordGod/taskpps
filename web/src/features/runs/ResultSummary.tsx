import { ClipboardList } from 'lucide-react';
import StatusTag from '@/components/StatusTag';
import { FONT_MONO, INK, STATUS_TEXT_COLOR } from '@/features/pipelines/nodes/nodeTokens';
import type { ResultPageResponse, RunStatus } from '@/types';

interface ResultSummaryProps {
  data: ResultPageResponse;
}

/** 时间格式化：内嵌渲染时用浏览器本地时区，比服务端预格式化更符合用户预期 */
function formatTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', { hour12: false });
}

/** 通过率配色：有失败用红、有阻塞用琥珀、否则绿
 * v2 (2026-09): 改用 STATUS_TEXT_COLOR 深色版本满足 WCAG 对比度（正文 4.5:1）
 */
function rateColor(failCount: number, blockedCount: number): string {
  if (failCount > 0) return STATUS_TEXT_COLOR.failed;
  if (blockedCount > 0) return STATUS_TEXT_COLOR.skipped;
  return STATUS_TEXT_COLOR.success;
}

/**
 * 默认结果页摘要（原生 React 渲染）
 *
 * 设计决策：不再把后端生成的手写 HTML 整段注入页面，避免外部样式污染应用，
 * 同时复用应用设计 token（工程蓝图：发丝边框、等宽技术文本、状态色）保持视觉一致。
 * 插件产物仍由 ResultViewer 以消毒后的 HTML/MD 形式渲染。
 *
 * v2 (2026-09, 参考 ui-ux-pro-max):
 * - 可访问性：状态数字/进度条改用高对比色，标签色从 slate-400 提到 slate-500
 * - 数据可视化：进度条补 role=img + aria-label + 分段 tooltip，避免仅靠颜色传达
 * - 空状态：无任务时给出说明文案，而不是一排 0
 *
 * v3 (2026-09, 用户反馈“太空旷”):
 * - 去掉内层卡片与 mx-auto 限宽，铺满已有的面板边框，避免卡片套卡片
 * - 指标从 4 个居中大格改为内联「值 + 标签」，时间从独立页脚上移到标题行
 * - 行高与内边距收紧（py-2.5 / py-3），整体高度约减半，信息密度对齐仪表盘
 */
export default function ResultSummary({ data }: ResultSummaryProps) {
  const s = data.stats;
  const total = Math.max(s.total_count, 0);
  const passPct = total > 0 ? (s.pass_count / total) * 100 : 0;
  const otherCount = Math.max(total - s.pass_count - s.fail_count - s.blocked_count, 0);
  const accent = rateColor(s.fail_count, s.blocked_count);

  const segments = [
    { key: 'pass', label: '通过', value: s.pass_count, color: STATUS_TEXT_COLOR.success },
    { key: 'fail', label: '失败', value: s.fail_count, color: STATUS_TEXT_COLOR.failed },
    { key: 'block', label: '阻塞', value: s.blocked_count, color: STATUS_TEXT_COLOR.skipped },
    { key: 'other', label: '其他', value: otherCount, color: INK.textSecondary },
  ];
  const metrics = [
    { key: 'pass', label: '通过', value: s.pass_count, color: STATUS_TEXT_COLOR.success },
    { key: 'fail', label: '失败', value: s.fail_count, color: STATUS_TEXT_COLOR.failed },
    { key: 'block', label: '阻塞', value: s.blocked_count, color: STATUS_TEXT_COLOR.skipped },
    { key: 'total', label: '总计', value: s.total_count, color: INK.textPrimary },
  ];
  const barLabel = `任务分布：通过 ${s.pass_count}，失败 ${s.fail_count}，阻塞 ${s.blocked_count}，总计 ${s.total_count}`;

  return (
    <div className="border-b border-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-3.5 w-[3px] shrink-0 rounded-full" style={{ background: accent }} />
          <span className="truncate font-mono text-sm font-medium text-slate-900">
            {data.pipeline_name}
          </span>
          <StatusTag status={data.status as RunStatus} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
          <span>
            <span className="text-slate-500">耗时 </span>
            {s.duration || '-'}
          </span>
          <span>
            <span className="text-slate-500">开始 </span>
            {formatTime(s.started_at)}
          </span>
          <span>
            <span className="text-slate-500">结束 </span>
            {formatTime(s.finished_at)}
          </span>
        </div>
      </div>

      {total === 0 ? (
        <div className="flex items-center justify-center gap-2 border-t border-slate-100 px-4 py-8 text-sm text-slate-500">
          <ClipboardList size={16} className="text-slate-300" aria-hidden="true" />
          本次运行没有任务记录
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-slate-100 px-4 py-3">
            <div className="flex items-baseline gap-1.5">
              <span
                className="text-2xl font-semibold leading-none tabular-nums"
                style={{ color: accent, fontFamily: FONT_MONO }}
              >
                {passPct.toFixed(1)}%
              </span>
              <span className="text-xs text-slate-500">通过率</span>
            </div>
            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
              {metrics.map((item) => (
                <span key={item.key} className="inline-flex items-baseline gap-1.5">
                  <span
                    className="text-base font-semibold tabular-nums"
                    style={{ color: item.color, fontFamily: FONT_MONO }}
                  >
                    {item.value}
                  </span>
                  <span className="text-xs text-slate-500">{item.label}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="px-4 pb-3">
            <div
              role="img"
              aria-label={barLabel}
              className="flex h-1.5 w-full overflow-hidden rounded-full bg-slate-100"
            >
              {segments.map((seg) =>
                seg.value > 0 ? (
                  <span
                    key={seg.key}
                    title={`${seg.label} ${seg.value}`}
                    className="h-full"
                    style={{ width: `${(seg.value / total) * 100}%`, background: seg.color }}
                  />
                ) : null,
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
