import { useState } from 'react';
import { Table, Select, Input, DatePicker, Space, Button, Modal, Form, Radio, InputNumber, App } from 'antd';
import { useNavigate } from 'react-router-dom';
import { Eye, Play, Trash2 } from 'lucide-react';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import { useRuns, useCleanRuns } from '@/api/runs';
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
function formatDuration(start: string | null, end: string | null) {
  if (!start) return '-';
  const s = dayjs(start);
  const e = end ? dayjs(end) : dayjs();
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
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [cleanOpen, setCleanOpen] = useState(false);
  const [cleanForm] = Form.useForm();
  const cleanRuns = useCleanRuns();

  const { data, isLoading } = useRuns();

  // 前端过滤
  const filtered = (data?.items ?? []).filter((run) => {
    if (statusFilter && run.status !== statusFilter) return false;
    if (pipelineFilter && !run.pipeline_name.toLowerCase().includes(pipelineFilter.toLowerCase())) return false;
    if (dateRange) {
      const created = dayjs(run.created_at);
      if (created.isBefore(dateRange[0]) || created.isAfter(dateRange[1])) return false;
    }
    return true;
  });

  // 打开清理弹窗时重置表单
  const handleOpenClean = () => {
    cleanForm.resetFields();
    setCleanOpen(true);
  };

  // 提交清理
  const handleClean = async () => {
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
  };

  const columns = [
    {
      title: 'Run ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <a onClick={() => navigate(`/runs/${id}`)} style={{ fontFamily: 'monospace' }}>
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
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: RunStatus) => <StatusTag status={status} />,
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
      render: (_: unknown, record: RunResponse) => formatDuration(record.started_at, record.finished_at),
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: RunResponse) => (
        <Button type="link" icon={<Eye size={14} />} onClick={() => navigate(`/runs/${record.id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div className="p-4">
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
      <Table<RunResponse>
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        loading={isLoading}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
      />

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
    </div>
  );
}
