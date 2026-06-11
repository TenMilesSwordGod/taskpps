import { Card, Col, Row, Statistic, Table, Tag } from 'antd';
import { GitBranch, Play, Loader, AlertCircle } from 'lucide-react';
import dayjs from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { usePipelines } from '@/api/pipelines';
import { useRuns } from '@/api/runs';
import { useHealthCheck } from '@/api/health';
import StatusTag from '@/components/StatusTag';
import type { RunResponse, RunStatus } from '@/types';

/** 计算耗时 */
function formatDuration(run: RunResponse): string {
  if (!run.started_at) return '-';
  const start = dayjs(run.started_at);
  const end = run.finished_at ? dayjs(run.finished_at) : dayjs();
  const sec = end.diff(start, 'second');
  if (sec < 60) return `${sec}秒`;
  const min = Math.floor(sec / 60);
  const remainSec = sec % 60;
  return `${min}分${remainSec}秒`;
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { data: pipelinesData } = usePipelines();
  const { data: runsData } = useRuns({ limit: 100 });
  const { data: healthData } = useHealthCheck();

  const pipelines = pipelinesData?.items ?? [];
  const runs = runsData?.items ?? [];

  // 统计数据
  const pipelineCount = pipelines.length;
  const todayRuns = runs.filter((r) => dayjs(r.created_at).isSame(dayjs(), 'day')).length;
  const runningCount = runs.filter((r) => r.status === 'running').length;
  const failedCount = runs.filter((r) => r.status === 'failed').length;

  // 最近 10 条运行
  const recentRuns = runs.slice(0, 10);

  const columns = [
    { title: '流水线', dataIndex: 'pipeline_name', key: 'pipeline_name' },
    {
      title: '项目',
      dataIndex: 'project_id',
      key: 'project_id',
      width: 110,
      render: (pid: string | null) =>
        pid ? <Tag style={{ fontFamily: 'monospace', fontSize: 11 }}>{pid}</Tag> : <span style={{ color: '#9ca3af' }}>默认</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (_status: RunStatus, record: RunResponse) => (
        <StatusTag status={record.status} error={record.error} />
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (v: string | null) => (v ? dayjs(v).format('HH:mm:ss') : '-'),
    },
    {
      title: '耗时',
      key: 'duration',
      render: (_: unknown, record: RunResponse) => formatDuration(record),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: RunResponse) => (
        <a onClick={() => navigate(`/runs/${record.id}`)}>查看</a>
      ),
    },
  ];

  return (
    <div className="p-4 space-y-4">
      {/* 统计卡片 */}
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="流水线总数" value={pipelineCount} prefix={<GitBranch size={18} />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日运行" value={todayRuns} prefix={<Play size={18} />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="运行中" value={runningCount} prefix={<Loader size={18} />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="失败" value={failedCount} prefix={<AlertCircle size={18} />} valueStyle={failedCount > 0 ? { color: '#cf1322' } : undefined} />
          </Card>
        </Col>
      </Row>

      {/* 最近运行 */}
      <Card title="最近运行">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={recentRuns}
          pagination={false}
          size="small"
        />
      </Card>

      {/* 服务器健康状态 */}
      <Card title="服务器状态" size="small" className="max-w-xs">
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-3 h-3 rounded-full"
            style={{ backgroundColor: healthData?.status === 'ok' ? '#52c41a' : '#ff4d4f' }}
          />
          <span>{healthData?.status === 'ok' ? '正常' : '异常'}</span>
          {healthData?.host && (
            <span className="text-gray-500 text-xs font-mono">
              {healthData.host}:{healthData.port}
            </span>
          )}
          {healthData?.version && <span className="text-gray-400 ml-2">v{healthData.version}</span>}
        </div>
      </Card>
    </div>
  );
}
