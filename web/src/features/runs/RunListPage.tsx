import { useState, useMemo, useCallback, useEffect } from 'react';
import { Table, Select, Input, DatePicker, Space, Button, Modal, Form, Radio, InputNumber, App, Tag } from 'antd';
import { useNavigate } from 'react-router-dom';
import { Eye, Play, Trash2 } from 'lucide-react';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import { useRuns, useCleanRuns, useDeleteRun } from '@/api/runs';
import StatusTag from '@/components/StatusTag';
import TriggerRunModal from '@/components/TriggerRunModal';
import type { RunResponse, RunStatus } from '@/types';

dayjs.extend(duration);

/** 运行状态选项 */
const STATUS_OPTIONS: { label: string; value: RunStatus }[] = [
  { label: '等待中', value: 'pending' },
  { label: '运行中', value: 'running' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
  { label: '部分完成', value: 'partial' },
];

/** 计算耗时 */
function formatDuration(start: string | null, end: string | null, nowTs?: number) {
  if (!start) return '-';
  const s = dayjs(start.endsWith('Z') || start.includes('+') ? start : start + 'Z');
  const e = end ? dayjs(end.endsWith('Z') || end.includes('+') ? end : end + 'Z') : dayjs(nowTs || undefined);
  const ms = e.diff(s);
  const d = dayjs.duration(ms);
  if (d.asHours() >= 1) return `${Math.floor(d.asHours())}h ${d.minutes()}m`;
  if (d.asMinutes() >= 1) return `${d.minutes()}m ${d.seconds()}s`;
  return `${d.seconds()}s`;
}

/** 运行历史页面 */
export default function RunListPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [statusFilter, setStatusFilter] = useState<RunStatus | undefined>();
  const [pipelineFilter, setPipelineFilter] = useState('');
  const [projectFilter, setProjectFilter] = useState('');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [cleanOpen, setCleanOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [cleanForm] = Form.useForm();
  const cleanRuns = useCleanRuns();
  const deleteRun = useDeleteRun();

  const { data, isLoading } = useRuns();

  // 实时刷新运行中任务的耗时
  const [now, setNow] = useState(Date.now());
  const hasRunning = useMemo(
    () => (data?.items ?? []).some((r) => r.status === 'running'),
    [data?.items],
  );
  useEffect(() => {
    if (!hasRunning) return;
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, [hasRunning]);

  // 前端过滤
  const filtered = useMemo(() => {
    const all = data?.items ?? [];
    if (!statusFilter && !pipelineFilter && !projectFilter && !dateRange) return all;
    const kw = pipelineFilter.toLowerCase();
    const pkw = projectFilter.toLowerCase();
    return all.filter((run) => {
      if (statusFilter && run.status !== statusFilter) return false;
      if (kw && !run.pipeline_name.toLowerCase().includes(kw)) return false;
      if (pkw && !(run.project_id || '').toLowerCase().includes(pkw)) return false;
      if (dateRange) {
        const created = dayjs(run.created_at);
        if (created.isBefore(dateRange[0]) || created.isAfter(dateRange[1])) return false;
      }
      return true;
    });
  }, [data?.items, statusFilter, pipelineFilter, projectFilter, dateRange]);

  // 打开清理弹窗时重置表单
  const handleOpenClean = useCallback(() => {
    cleanForm.resetFields();
    setCleanOpen(true);
  }, [cleanForm]);

  // 提交清理
  const handleClean = useCallback(async () => {
    try {
      const values = await cleanForm.validateFields();
      const params: { older_than?: number; keep?: number; force?: boolean } = {};
      if (values.mode === 'older_than') params.older_than = values.older_than;
      else if (values.mode === 'keep') params.keep = values.keep;
      else if (values.mode === 'force') params.force = true;

      const result = await cleanRuns.mutateAsync(params);
      message.success(`已清理 ${result.deleted_runs} 条历史运行，删除 ${result.deleted_logs} 个日志文件`);
      setCleanOpen(false);
    } catch {
      // 校验失败或请求失败（mutation onError 处理）
    }
  }, [cleanForm, cleanRuns, message]);

  // 稳定化：Table 不必要的重建
  const handleOpenDetail = useCallback(
    (id: string) => navigate(`/runs/${id}`),
    [navigate],
  );

  const handleDeleteSingle = useCallback(
    (id: string) => {
      setDeleteTargetId(id);
    },
    [],
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTargetId) return;
    try {
      await deleteRun.mutateAsync(deleteTargetId);
      message.success('已删除');
      setDeleteTargetId(null);
    } catch {
      message.error('删除失败');
    }
  }, [deleteTargetId, deleteRun, message]);

  const columns = useMemo(() => [
    {
      title: 'Run ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <a onClick={() => handleOpenDetail(id)} style={{ fontFamily: 'monospace' }}>
          {id.slice(0, 8)}
        </a>
      ),
    },
    {
      title: '流水线名',
      dataIndex: 'pipeline_name',
      key: 'pipeline_name',
    },
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
      width: 120,
      render: (_status: RunStatus, record: RunResponse) => (
        <StatusTag status={record.status} error={record.error} />
      ),
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      width: 180,
      render: (v: string | null) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '耗时',
      key: 'duration',
      width: 120,
      render: (_: unknown, record: RunResponse) => formatDuration(record.started_at, record.finished_at, now),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      render: (_: unknown, record: RunResponse) => (
        <Space size={4}>
          <Button type="link" size="small" icon={<Eye size={14} />} onClick={() => handleOpenDetail(record.id)}>
            查看
          </Button>
          <Button type="link" size="small" danger icon={<Trash2 size={14} />} onClick={() => handleDeleteSingle(record.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ], [handleOpenDetail, now]);

  return (
    <div className="flex flex-col h-full p-4 overflow-hidden">
      {/* 过滤栏 */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear
          placeholder="状态筛选"
          value={statusFilter}
          onChange={setStatusFilter}
          style={{ width: 140 }}
          options={STATUS_OPTIONS}
        />
        <Input
          placeholder="流水线名"
          value={pipelineFilter}
          onChange={(e) => setPipelineFilter(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
        <Input
          placeholder="项目"
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          style={{ width: 120 }}
          allowClear
        />
        <DatePicker.RangePicker
          value={dateRange}
          onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs] | null)}
          showTime
        />
        <Button type="primary" icon={<Play size={14} />} onClick={() => setTriggerOpen(true)}>
          触发运行
        </Button>
        <Button icon={<Trash2 size={14} />} danger onClick={handleOpenClean}>
          删除历史
        </Button>
      </Space>

      {/* 表格 */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <Table<RunResponse>
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          loading={isLoading}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条`, size: 'small' }}
          size="small"
          scroll={{ y: 'calc(100vh - 320px)' }}
        />
      </div>

      <TriggerRunModal open={triggerOpen} onClose={() => setTriggerOpen(false)} />

      {/* 删除历史弹窗 */}
      <Modal
        title="删除历史运行"
        open={cleanOpen}
        onOk={handleClean}
        onCancel={() => setCleanOpen(false)}
        confirmLoading={cleanRuns.isPending}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        destroyOnClose
      >
        <Form
          form={cleanForm}
          layout="vertical"
          initialValues={{ mode: 'older_than', older_than: 7, keep: 50 }}
        >
          <Form.Item name="mode" label="清理方式">
            <Radio.Group>
              <Space direction="vertical">
                <Radio value="older_than">仅保留最近 N 天的运行</Radio>
                <Radio value="keep">仅保留最近 N 条运行</Radio>
                <Radio value="force">清空所有历史运行</Radio>
              </Space>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            noStyle
            shouldUpdate={(prev, curr) => prev.mode !== curr.mode}
          >
            {({ getFieldValue }) => {
              const mode = getFieldValue('mode');
              if (mode === 'older_than') {
                return (
                  <Form.Item
                    name="older_than"
                    label="保留天数"
                    rules={[{ required: true, message: '请输入天数' }]}
                  >
                    <InputNumber min={1} max={365} addonAfter="天" style={{ width: 200 }} />
                  </Form.Item>
                );
              }
              if (mode === 'keep') {
                return (
                  <Form.Item
                    name="keep"
                    label="保留条数"
                    rules={[{ required: true, message: '请输入条数' }]}
                  >
                    <InputNumber min={0} max={10000} addonAfter="条" style={{ width: 200 }} />
                  </Form.Item>
                );
              }
              return null;
            }}
          </Form.Item>

          <div style={{ color: '#999', fontSize: 12 }}>
            注意：删除操作会同时清理对应的任务日志文件，且不可恢复。
          </div>
        </Form>
      </Modal>

      {/* 删除单条确认弹窗 */}
      <Modal
        title="确认删除"
        open={deleteTargetId !== null}
        onOk={handleDeleteConfirm}
        onCancel={() => setDeleteTargetId(null)}
        confirmLoading={deleteRun.isPending}
        okText="删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        destroyOnClose
      >
        删除后不可恢复，确认删除该运行记录？
      </Modal>
    </div>
  );
}
