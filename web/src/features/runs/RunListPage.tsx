import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { Table, Input, DatePicker, Space, Button, Modal, Form, Radio, InputNumber, App, Tag, Tooltip, Segmented, TreeSelect, Popconfirm } from 'antd';
import { useNavigate } from 'react-router-dom';
import { Eye, Play, Trash2, RefreshCw, History, CircleDot, Search } from 'lucide-react';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import { useRuns, useRunStats, useCleanRuns, useDeleteRun } from '@/api/runs';
import StatusTag from '@/components/StatusTag';
import PipelineProgressPopover from '@/components/PipelineProgressPopover';
import TriggerRunModal from '@/components/TriggerRunModal';
import type { RunResponse, RunStatus } from '@/types';

dayjs.extend(duration);

/** 状态过滤选项（Segmented 用） */
const STATUS_OPTIONS: { label: string; value: RunStatus | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
  { label: '部分完成', value: 'partial' },
];

/** 计算耗时（基于服务端返回的 duration_ms） */
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

/** 运行状态对应的行背景色（轻量提示） */
function rowBackground(status: RunStatus): string | undefined {
  if (status === 'running') return 'rgba(126, 173, 255, 0.08)';
  if (status === 'failed') return 'rgba(239, 68, 68, 0.04)';
  return undefined;
}

/** 运行历史页面 */
export default function RunListPage() {
  const navigate = useNavigate();
  const { message } = App.useApp();
  const tableContainerRef = useRef<HTMLDivElement>(null);
  const [tableScrollY, setTableScrollY] = useState<number | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<RunStatus | 'all'>('all');
  const [globalSearch, setGlobalSearch] = useState('');
  const [treeSelectValue, setTreeSelectValue] = useState<string | undefined>(undefined);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [cleanOpen, setCleanOpen] = useState(false);
  const [cleanForm] = Form.useForm();
  const cleanRuns = useCleanRuns();
  const deleteRun = useDeleteRun();

  const { data, isLoading, refetch, isFetching } = useRuns();
  const { data: statsData } = useRunStats();

  // 动态计算表格滚动高度，避免页面出现滚动条
  useEffect(() => {
    const container = tableContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        // 表格容器高度 - 表格头(约39px) - 分页(约56px) - 边距
        const h = Math.floor(entry.contentRect.height) - 100;
        setTableScrollY(Math.max(h, 200));
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const allItems = useMemo(() => data?.items ?? [], [data?.items]);

  // 统计胶囊（来自后端全量统计 API）
  const stats = useMemo(() => statsData ?? { total: 0, pending: 0, running: 0, success: 0, failed: 0, cancelled: 0, partial: 0 }, [statsData]);

  // 构建项目>流水线树形数据（用于 TreeSelect）
  const treeData = useMemo(() => {
    const projectMap = new Map<string, { name: string; pipelines: Map<string, string> }>();
    for (const r of allItems) {
      const projKey = r.project_id || '__default__';
      const projName = r.project_id ? (r.project_name || r.project_id) : '默认项目';
      if (!projectMap.has(projKey)) {
        projectMap.set(projKey, { name: projName, pipelines: new Map() });
      }
      if (r.pipeline_name) {
        projectMap.get(projKey)!.pipelines.set(r.pipeline_name, r.pipeline_name);
      }
    }
    return Array.from(projectMap.entries()).map(([projKey, { name, pipelines }]) => ({
      title: name,
      value: projKey,
      key: projKey,
      children: Array.from(pipelines.entries()).map(([pipeName, pipeLabel]) => ({
        title: pipeLabel,
        value: `${projKey}::${pipeName}`,
        key: `${projKey}::${pipeName}`,
      })),
    }));
  }, [allItems]);

  // 从 treeSelectValue 解析出 projectFilter 和 pipelineFilter
  const { projectFilter, pipelineFilter } = useMemo(() => {
    if (!treeSelectValue) return { projectFilter: null, pipelineFilter: null };
    if (treeSelectValue.includes('::')) {
      const [proj, pipe] = treeSelectValue.split('::');
      return { projectFilter: proj === '__default__' ? null : proj, pipelineFilter: pipe };
    }
    return { projectFilter: treeSelectValue === '__default__' ? null : treeSelectValue, pipelineFilter: null };
  }, [treeSelectValue]);

  // 前端过滤
  const filtered = useMemo(() => {
    const kw = globalSearch.toLowerCase();
    return allItems.filter((run) => {
      if (statusFilter !== 'all' && run.status !== statusFilter) return false;
      if (projectFilter && run.project_id !== projectFilter) return false;
      if (pipelineFilter && run.pipeline_name !== pipelineFilter) return false;
      if (dateRange) {
        const created = dayjs(run.created_at);
        if (created.isBefore(dateRange[0]) || created.isAfter(dateRange[1])) return false;
      }
      if (kw) {
        const searchFields = [
          run.display_name,
          run.id,
          run.pipeline_name,
          run.project_name,
          run.project_id,
        ].filter(Boolean);
        if (!searchFields.some(f => f!.toLowerCase().includes(kw))) return false;
      }
      return true;
    });
  }, [allItems, statusFilter, globalSearch, projectFilter, pipelineFilter, dateRange]);

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

  const handleDeleteConfirm = useCallback(async (id: string) => {
    try {
      await deleteRun.mutateAsync(id);
      message.success('已删除');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '删除失败';
      message.error(msg);
    }
  }, [deleteRun, message]);

  const columns = useMemo(() => [
    {
      title: '运行名',
      dataIndex: 'display_name',
      key: 'display_name',
      width: 140,
      render: (_: string, record: RunResponse) => (
        <PipelineProgressPopover runId={record.id} tasks={record.tasks} taskSummary={record.task_summary}>
          <a onClick={() => handleOpenDetail(record.id)} style={{ color: '#3D5BFF', fontWeight: 500 }}>
            {record.display_name || record.id.slice(0, 8)}
          </a>
        </PipelineProgressPopover>
      ),
    },
    {
      title: '流水线名',
      dataIndex: 'pipeline_name',
      key: 'pipeline_name',
      ellipsis: true,
    },
    {
      title: '文件',
      dataIndex: 'pipeline_file',
      key: 'pipeline_file',
      width: 180,
      render: (_file: string, record: RunResponse) => (
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#7C7F88' }}>
          {record.definition_id || _file}
        </span>
      ),
    },
    {
      title: '项目',
      dataIndex: 'project_id',
      key: 'project_id',
      width: 110,
      render: (_: string | null, record: RunResponse) =>
        record.project_name ? <Tag style={{ borderRadius: 3 }}>{record.project_name}</Tag> : record.project_id ? <Tag style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, borderRadius: 3 }}>{record.project_id}</Tag> : <span style={{ color: '#7C7F88' }}>默认</span>,
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
      render: (_: unknown, record: RunResponse) => formatDuration(record.duration_ms),
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
          <Popconfirm
            title="确认删除"
            description="删除后不可恢复，确认删除该运行记录？"
            onConfirm={() => handleDeleteConfirm(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button data-testid="row-delete-btn" type="link" size="small" danger icon={<Trash2 size={14} />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ], [handleOpenDetail, handleDeleteConfirm]);

  return (
    <div className="flex flex-col h-full p-6 gap-3 overflow-hidden" style={{ background: '#F6F6F8' }}>
      {/* 顶部工具栏 */}
      <div className="shrink-0 px-5 py-3 flex items-center justify-between gap-3 flex-wrap" style={{ background: '#FFFFFF', borderRadius: 8, border: '1px solid #E3E4E8', boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px' }}>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <History size={18} color="#7C7F88" />
            <span className="text-base font-semibold" style={{ color: '#121620' }}>运行历史</span>
          </div>
          {/* 统计胶囊 */}
          <div className="flex items-center gap-2 text-xs">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: '#F6F6F8', color: '#7C7F88' }}>
              总计 {stats.total}
            </span>
            {stats.pending > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: '#F6F6F8', color: '#7C7F88' }}>
                <CircleDot size={10} color="#7C7F88" />
                等待中 {stats.pending}
              </span>
            )}
            {stats.running > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: 'rgba(126, 173, 255, 0.12)', color: '#3D5BFF' }}>
                <CircleDot size={10} color="#7EADFF" className="animate-pulse" />
                运行中 {stats.running}
              </span>
            )}
            {stats.success > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: 'rgba(16, 185, 129, 0.08)', color: '#10b981' }}>
                <CircleDot size={10} color="#10b981" />
                成功 {stats.success}
              </span>
            )}
            {stats.failed > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: 'rgba(239, 68, 68, 0.06)', color: '#ef4444' }}>
                <CircleDot size={10} color="#ef4444" />
                失败 {stats.failed}
              </span>
            )}
            {stats.cancelled > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: 'rgba(249, 115, 22, 0.08)', color: '#f97316' }}>
                <CircleDot size={10} color="#f97316" />
                已取消 {stats.cancelled}
              </span>
            )}
            {stats.partial > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: 'rgba(126, 173, 255, 0.08)', color: '#7EADFF' }}>
                <CircleDot size={10} color="#7EADFF" />
                部分完成 {stats.partial}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Tooltip title="手动刷新">
            <Button
              size="small"
              icon={<RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />}
              onClick={() => refetch()}
              disabled={isFetching}
            >
              刷新
            </Button>
          </Tooltip>
          <Button type="primary" size="small" icon={<Play size={14} />} onClick={() => setTriggerOpen(true)}>
            触发运行
          </Button>
          <Button size="small" icon={<Trash2 size={14} />} danger onClick={handleOpenClean}>
            删除历史
          </Button>
        </div>
      </div>

      {/* 过滤栏 */}
      <div className="shrink-0 px-5 py-2.5 flex items-center gap-2 flex-wrap" style={{ background: '#FFFFFF', borderRadius: 8, border: '1px solid #E3E4E8' }}>
        <Segmented
          size="small"
          options={STATUS_OPTIONS}
          value={statusFilter}
          onChange={(v) => setStatusFilter(v as RunStatus | 'all')}
        />
        <span style={{ color: '#E3E4E8' }}>|</span>
        <TreeSelect
          allowClear
          showSearch
          treeDefaultExpandAll={false}
          placeholder="项目 / 流水线"
          value={treeSelectValue}
          onChange={(v: string) => setTreeSelectValue(v ?? undefined)}
          treeData={treeData}
          style={{ width: 220 }}
          treeNodeFilterProp="title"
        />
        <DatePicker.RangePicker
          size="small"
          value={dateRange}
          onChange={(v) => setDateRange(v as [dayjs.Dayjs, dayjs.Dayjs] | null)}
          showTime
        />
        <div className="flex-1" />
        <Input
          allowClear
          prefix={<Search size={14} color="#7C7F88" />}
          placeholder="搜索运行名称 / UUID / 项目 / 流水线"
          value={globalSearch}
          onChange={(e) => setGlobalSearch(e.target.value)}
          style={{ width: 280 }}
        />
      </div>

      {/* 表格 */}
      <div ref={tableContainerRef} className="runs-table-container flex-1 min-h-0 overflow-hidden">
        <Table<RunResponse>
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          loading={isLoading}
          pagination={{ pageSize: 12, showSizeChanger: true, pageSizeOptions: [12, 20, 50, 100], showTotal: (t) => `共 ${t} 条`, size: 'small' }}
          size="small"
          scroll={tableScrollY ? { y: tableScrollY } : undefined}
          onRow={(record) => ({
            style: rowBackground(record.status) ? { background: rowBackground(record.status) } : undefined,
          })}
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
        destroyOnHidden
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

          <div style={{ color: '#7C7F88', fontSize: 12 }}>
            注意：删除操作会同时清理对应的任务日志文件，且不可恢复。
          </div>
        </Form>
      </Modal>
    </div>
  );
}
