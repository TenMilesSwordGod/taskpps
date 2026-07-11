import { Card, Col, Row, Statistic, Table, Tag, Button } from 'antd';
import type { CSSProperties } from 'react';
import { useMemo } from 'react';
import { GitBranch, Play, Loader, AlertCircle, History } from 'lucide-react';
import dayjs from 'dayjs';
import { useNavigate } from 'react-router-dom';
import { usePipelines } from '@/api/pipelines';
import { useRuns } from '@/api/runs';
import { useHealthCheck } from '@/api/health';
import StatusTag from '@/components/StatusTag';
import PipelineProgressPopover from '@/components/PipelineProgressPopover';
import type { RunResponse, RunStatus } from '@/types';

/** 计算耗时（基于服务端返回的 duration_ms） */
function formatDuration(durationMs: number | null): string {
  if (durationMs == null || durationMs < 0) return '-';
  const sec = Math.floor(durationMs / 1000);
  if (sec < 60) return `${sec}秒`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const remainSec = sec % 60;
  if (h > 0) return `${h}时${m}分${remainSec}秒`;
  return `${m}分${remainSec}秒`;
}

/** 运行状态对应的行背景色 — Column 风格浅色提示 */
function rowBackground(status: RunStatus): string | undefined {
  if (status === 'running') return 'rgba(126, 173, 255, 0.08)';
  if (status === 'failed') return 'rgba(239, 68, 68, 0.04)';
  return undefined;
}

/** Column 风格统计卡片 */
const statCardStyle: CSSProperties = {
  border: '1px solid #E3E4E8',
  borderRadius: 8,
  boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
};

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

  const columns = useMemo(() => [
    {
      title: '运行名',
      dataIndex: 'display_name',
      key: 'display_name',
      width: 120,
      render: (_: string, record: RunResponse) => (
        <PipelineProgressPopover runId={record.id} tasks={record.tasks} taskSummary={record.task_summary}>
          <a onClick={() => navigate(`/runs/${record.id}`)} style={{ color: '#3D5BFF', fontWeight: 500 }}>
            {record.display_name || record.id.slice(0, 8)}
          </a>
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
      render: (_: unknown, record: RunResponse) => formatDuration(record.duration_ms),
    },
  ], [navigate]);

  return (
    <div className="p-6 space-y-4 overflow-auto h-full">
      {/* 统计卡片 */}
      <Row gutter={24}>
        <Col span={6}>
          <Card style={statCardStyle} styles={{ body: { padding: 20 } }}>
            <Statistic
              title="流水线总数"
              value={pipelineCount}
              prefix={<GitBranch size={18} color="#7C7F88" />}
              valueStyle={{ color: '#121620', fontWeight: 500 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card style={statCardStyle} styles={{ body: { padding: 20 } }}>
            <Statistic
              title="今日运行"
              value={todayRuns}
              prefix={<Play size={18} color="#7C7F88" />}
              valueStyle={{ color: '#121620', fontWeight: 500 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card style={statCardStyle} styles={{ body: { padding: 20 } }}>
            <Statistic
              title="运行中"
              value={runningCount}
              prefix={<Loader size={18} color="#7EADFF" />}
              valueStyle={{ color: '#3D5BFF', fontWeight: 500 }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card style={statCardStyle} styles={{ body: { padding: 20 } }}>
            <Statistic
              title="失败"
              value={failedCount}
              prefix={<AlertCircle size={18} color={failedCount > 0 ? '#ef4444' : '#7C7F88'} />}
              valueStyle={failedCount > 0 ? { color: '#ef4444', fontWeight: 500 } : { color: '#121620', fontWeight: 500 }}
            />
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

      {/* 服务器健康状态 */}
      <Card
        title="服务器状态"
        size="small"
        className="max-w-xs"
        style={{
          border: '1px solid #E3E4E8',
          borderRadius: 8,
          boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
        }}
      >
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{
              backgroundColor: healthData?.status === 'ok' ? '#10b981' : '#ef4444',
              boxShadow: healthData?.status === 'ok' ? '0 0 6px rgba(16, 185, 129, 0.4)' : 'none',
            }}
          />
          <span style={{ color: '#121620', fontWeight: 500 }}>
            {healthData?.status === 'ok' ? '正常' : '异常'}
          </span>
          {healthData?.host && (
            <span style={{ color: '#7C7F88', fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}>
              {healthData.host}:{healthData.port}
            </span>
          )}
          {healthData?.version && (
            <span style={{ color: '#7C7F88', fontSize: 12, marginLeft: 8 }}>
              v{healthData.version}
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}