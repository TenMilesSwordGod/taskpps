import { Card, Col, Row, Statistic, Table, Tag, Button, Select, Segmented, Alert, Skeleton } from 'antd';
import type { CSSProperties, ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { GitBranch, Play, Loader, AlertCircle, History, RefreshCw } from 'lucide-react';
import dayjs from 'dayjs';
import { STATUS_COLOR } from '@/features/pipelines/nodes/nodeTokens';
import { useNavigate, Link } from 'react-router-dom';
import { usePipelines } from '@/api/pipelines';
import { useRuns } from '@/api/runs';
import { useProjects } from '@/api/projects';
import StatusTag from '@/components/StatusTag';
import PipelineProgressPopover from '@/components/PipelineProgressPopover';
import TrendLineChart from '@/features/dashboard/components/TrendLineChart';
import type { RunResponse, RunStatus } from '@/types';

/** 计算耗时（基于服务端返回的 duration_ms） */
/* 注意(2026-07): Bug #47 修复 — 从中文长格式改为简短 h/m/s 格式（与 RunListPage 保持一致），
   避免 "15时30分0秒" 这类长字符串在 90px 列宽内换行。同时增加 ellipsis 兜底。 */
function formatDuration(durationMs: number | null): string {
  if (durationMs == null || durationMs < 0) return '-';
  const totalSec = Math.floor(durationMs / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

/** 运行状态对应的行背景色 — Column 风格浅色提示 */
function rowBackground(status: RunStatus): string | undefined {
  if (status === 'running') return 'rgba(126, 173, 255, 0.08)';
  if (status === 'failed') return 'rgba(239, 68, 68, 0.04)';
  return undefined;
}

/** 运行状态配色（v2: 统一引用 nodeTokens STATUS_COLOR，移除本地硬编码） */
function runStatusColor(status: string): string {
  if (status === 'success' || status === 'failed' || status === 'running' || status === 'cancelled' || status === 'skipped') {
    return STATUS_COLOR[status as keyof typeof STATUS_COLOR];
  }
  if (status === 'pending') return STATUS_COLOR.pending;
  return STATUS_COLOR.cancelled; // partial 等未知状态用灰
}

/**
 * 单次运行的任务成功率（%）
 * 成功率 = success / (总任务数 - skipped)，分母为 0 时返回 0
 */
function taskSuccessRatePct(summary: Record<string, number> | undefined | null): number {
  if (!summary) return 0;
  const total = Object.values(summary).reduce((a, b) => a + b, 0);
  const skipped = summary.skipped ?? 0;
  const denom = total - skipped;
  if (denom <= 0) return 0;
  return Math.round(((summary.success ?? 0) / denom) * 100);
}

/** Column 风格统计卡片 */
const statCardStyle: CSSProperties = {
  border: '1px solid #E3E4E8',
  borderRadius: 8,
  boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
};

/**
 * 统计卡片（issue #217）。
 *
 * 设计决策（为什么这么写）：加载中渲染骨架而不是数字 0，
 * 避免首屏「0 → 真实值」跳变造成误读。
 */
function StatCard({
  title,
  value,
  icon,
  valueStyle,
  loading,
}: {
  title: string;
  value: number;
  icon: ReactNode;
  valueStyle?: CSSProperties;
  loading: boolean;
}) {
  return (
    <Card style={{ ...statCardStyle, height: '100%' }} styles={{ body: { padding: 16 } }}>
      {loading ? (
        <Skeleton active paragraph={{ rows: 1 }} title={false} />
      ) : (
        <Statistic title={title} value={value} prefix={icon} valueStyle={valueStyle} />
      )}
    </Card>
  );
}

const TREND_DAYS = 14;
const RECENT_RUNS_COUNT = 15;

type TrendView = 'daily' | 'recent';

export default function DashboardPage() {
  const navigate = useNavigate();
  const {
    data: pipelinesData,
    isLoading: pipelinesLoading,
    error: pipelinesError,
    refetch: refetchPipelines,
  } = usePipelines();
  const {
    data: runsData,
    isLoading: runsLoading,
    error: runsError,
    refetch: refetchRuns,
  } = useRuns({ limit: 500 });
  const {
    data: projectsData,
    isLoading: projectsLoading,
    error: projectsError,
    refetch: refetchProjects,
  } = useProjects();

  // v2 (2026-09, issue #217): 三种查询的加载/失败聚合，供统计卡骨架与错误提示使用
  const isLoading = pipelinesLoading || runsLoading || projectsLoading;
  const loadError = pipelinesError || runsError || projectsError;
  const refetchAll = () => {
    refetchPipelines();
    refetchRuns();
    refetchProjects();
  };

  const pipelines = useMemo(() => pipelinesData?.items ?? [], [pipelinesData]);
  const runs = useMemo(() => runsData?.items ?? [], [runsData]);
  const projects = projectsData ?? [];

  const [selectedProject, setSelectedProject] = useState<string>('all');
  const [trendView, setTrendView] = useState<TrendView>('recent');

  // 统计数据
  const pipelineCount = pipelines.length;
  const todayRuns = runs.filter((r) => dayjs(r.created_at).isSame(dayjs(), 'day')).length;
  const runningCount = runs.filter((r) => r.status === 'running').length;
  const failedCount = runs.filter((r) => r.status === 'failed').length;

  // 最近 10 条运行
  const recentRuns = runs.slice(0, 10);

  // 按天聚合的任务成功率（支持按项目过滤）：每日内所有运行的 pass 任务 / 总任务（剔除 skipped）
  const trend = (() => {
    const days = Array.from({ length: TREND_DAYS }, (_, i) =>
      dayjs().startOf('day').subtract(TREND_DAYS - 1 - i, 'day'),
    );
    const pass = new Array(TREND_DAYS).fill(0);
    const denom = new Array(TREND_DAYS).fill(0);
    // 收集每天出现的运行名（去重），供 tooltip 显示
    const dayNames: string[][] = Array.from({ length: TREND_DAYS }, () => []);
    for (const r of runs) {
      const d = dayjs(r.created_at).startOf('day');
      const idx = days.findIndex((day) => day.isSame(d, 'day'));
      if (idx < 0) continue;
      if (selectedProject !== 'all' && (r.project_id || '') !== selectedProject) continue;
      const total = Object.values(r.task_summary ?? {}).reduce((a, b) => a + b, 0);
      const skipped = r.task_summary?.skipped ?? 0;
      pass[idx] += r.task_summary?.success ?? 0;
      denom[idx] += Math.max(0, total - skipped);
      dayNames[idx].push(r.display_name || r.pipeline_name || r.id.slice(0, 8));
    }
    return days.map((day, i) => {
      const names = dayNames[i];
      const count = names.length;
      // 取前 3 个不重复名字，加「…」缩略
      let detail: string | undefined;
      if (count > 0) {
        const uniq = [...new Set(names)];
        detail = `共 ${count} 次${uniq.length > 0 ? '：' + uniq.slice(0, 3).join('、') : ''}${uniq.length > 3 ? '…' : ''}`;
      }
      return {
        label: day.format('MM-DD'),
        value: denom[i] > 0 ? Math.round((pass[i] / denom[i]) * 100) : 0,
        detail,
      };
    });
  })();

  // 最近 N 次运行（按时间正序，左→右为从早到晚），纵坐标为单次运行的任务成功率，
  // 每点附带运行状态/时间，供 tooltip 展示“跑的情况”
  const recentTrend = useMemo(() => {
    const filtered = runs.filter(
      (r) => selectedProject === 'all' || (r.project_id || '') === selectedProject,
    );
    return filtered
      .slice(0, RECENT_RUNS_COUNT)
      .map((r) => ({
        label: r.display_name || r.pipeline_name || r.id,
        value: taskSuccessRatePct(r.task_summary),
        status: r.status,
        statusColor: runStatusColor(r.status),
        time: r.started_at
          ? dayjs(r.started_at).format('MM-DD HH:mm')
          : dayjs(r.created_at).format('MM-DD HH:mm'),
        id: r.id,
      }))
      .reverse();
  }, [runs, selectedProject]);

  const trendData = trendView === 'daily' ? trend : recentTrend;
  const trendUnit = trendView === 'daily' ? '每日任务成功率' : '单次运行任务成功率';
  const trendUnitShort = '%';

  const projectOptions = [
    { value: 'all', label: '全部项目' },
    ...projects.map((p) => ({ value: p.id, label: p.name })),
  ];

  const columns = useMemo(() => [
    {
      title: '运行名',
      dataIndex: 'display_name',
      key: 'display_name',
      width: 220,
      render: (_: string, record: RunResponse) => (
        <PipelineProgressPopover runId={record.id} tasks={record.tasks} taskSummary={record.task_summary}>
          {/* v2 (2026-09, issue #219): 真实链接，键盘可聚焦 */}
          <Link to={`/runs/${record.id}`} style={{ color: '#3D5BFF', fontWeight: 500 }}>
            {record.display_name || record.id.slice(0, 8)}
          </Link>
        </PipelineProgressPopover>
      ),
    },
    {
      title: '流水线',
      dataIndex: 'pipeline_name',
      key: 'pipeline_name',
      ellipsis: true,
      render: (v: string) => <span style={{ color: '#121620' }}>{v}</span>,
    },
    {
      title: '项目',
      dataIndex: 'project_id',
      key: 'project_id',
      width: 100,
      render: (_: string | null, record: RunResponse) =>
        record.project_name ? (
          <Tag style={{ borderRadius: 3 }}>{record.project_name}</Tag>
        ) : record.project_id ? (
          <Tag style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, borderRadius: 3 }}>{record.project_id}</Tag>
        ) : (
          <span style={{ color: '#7C7F88' }}>默认</span>
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (_status: RunStatus, record: RunResponse) => (
        <StatusTag status={record.status} error={record.error} />
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 90,
      render: (v: string | null) => (v ? dayjs(v).format('HH:mm:ss') : '-'),
    },
    {
      title: '耗时',
      key: 'duration',
      width: 90,
      ellipsis: true,
      render: (_: unknown, record: RunResponse) => formatDuration(record.duration_ms),
    },
  // 注意(2026-09, issue #219): 运行名改为 <Link> 后列定义不再依赖 navigate，依赖数组清空
  ], []);

  return (
    <div className="p-6 space-y-4 overflow-auto h-full">
      {/* v2 (2026-09, issue #217): 手动刷新入口 + 加载失败提示 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button size="small" icon={<RefreshCw size={14} />} onClick={refetchAll} disabled={isLoading}>
          刷新
        </Button>
      </div>
      {loadError && (
        <Alert
          type="error"
          showIcon
          message="看板数据加载失败"
          description={loadError instanceof Error ? loadError.message : '请稍后重试'}
          action={
            <Button size="small" onClick={refetchAll}>
              重试
            </Button>
          }
        />
      )}
      <Row gutter={[16, 16]} align="stretch">
        {/* 左侧：2×2 统计卡片 */}
        <Col xs={24} lg={8}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gridTemplateRows: '1fr 1fr',
              gap: 12,
              height: '100%',
            }}
          >
            <StatCard
              title="流水线总数"
              value={pipelineCount}
              icon={<GitBranch size={18} color="#94A3B8" />}
              valueStyle={{ color: '#0F172A', fontWeight: 500 }}
              loading={isLoading}
            />
            <StatCard
              title="今日运行"
              value={todayRuns}
              icon={<Play size={18} color="#94A3B8" />}
              valueStyle={{ color: '#0F172A', fontWeight: 500 }}
              loading={isLoading}
            />
            <StatCard
              title="运行中"
              value={runningCount}
              icon={<Loader size={18} color={STATUS_COLOR.running} />}
              valueStyle={{ color: STATUS_COLOR.running, fontWeight: 500 }}
              loading={isLoading}
            />
            <StatCard
              title="失败"
              value={failedCount}
              icon={<AlertCircle size={18} color={failedCount > 0 ? STATUS_COLOR.failed : '#94A3B8'} />}
              valueStyle={failedCount > 0 ? { color: STATUS_COLOR.failed, fontWeight: 500 } : { color: '#0F172A', fontWeight: 500 }}
              loading={isLoading}
            />
          </div>
        </Col>

        {/* 右侧：运行走势 */}
        <Col xs={24} lg={16} style={{ display: 'flex' }}>
          <Card
            title="运行走势"
            extra={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Segmented
                  size="small"
                  value={trendView}
                  onChange={(v) => setTrendView(v as TrendView)}
                  options={[
                    { label: '近日', value: 'daily' },
                    { label: '近十五次', value: 'recent' },
                  ]}
                />
                <Select
                  size="small"
                  value={selectedProject}
                  onChange={setSelectedProject}
                  options={projectOptions}
                  style={{ width: 160 }}
                />
              </div>
            }
            style={{
              border: '1px solid #E3E4E8',
              borderRadius: 8,
              boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
            }}
            styles={{
              header: { borderBottom: '1px solid #E3E4E8', minHeight: 48, flex: 'none' },
              body: {
                flex: 1,
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
                padding: 12,
            } }}
          >
            <div style={{ flex: 1, minHeight: 180, position: 'relative' }}>
              <TrendLineChart
                data={trendData}
                height={220}
                unit={trendUnitShort}
                onPointClick={(id) => navigate(`/runs/${id}`)}
              />
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: '#7C7F88', textAlign: 'right', flex: 'none' }}>
              {trendUnit}
            </div>
          </Card>
        </Col>
      </Row>

      {/* 最近运行 */}
      <Card
        title="最近运行"
        extra={
          <Button type="link" size="small" icon={<History size={14} />} onClick={() => navigate('/runs')}>
            查看全部
          </Button>
        }
        style={{
          border: '1px solid #E3E4E8',
          borderRadius: 8,
          boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
        }}
        styles={{ header: { borderBottom: '1px solid #E3E4E8', minHeight: 48 } }}
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={recentRuns}
          pagination={false}
          size="small"
          onRow={(record) => ({
            style: rowBackground(record.status) ? { background: rowBackground(record.status), cursor: 'pointer' } : { cursor: 'pointer' },
            onClick: () => navigate(`/runs/${record.id}`),
          })}
        />
      </Card>
    </div>
  );
}
