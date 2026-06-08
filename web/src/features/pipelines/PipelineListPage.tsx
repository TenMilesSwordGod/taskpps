import { useState, useMemo } from 'react';
import { Card, Table, Button, Input, Space, Progress, Tooltip, message } from 'antd';
import { Search, RefreshCw, Play, Eye, Image } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { usePipelines } from '@/api/pipelines';
import StatusTag from '@/components/StatusTag';
import TriggerRunModal from '@/components/TriggerRunModal';
import type { PipelineSummary, RunStatus } from '@/types';

export default function PipelineListPage() {
  const navigate = useNavigate();
  const { data, isLoading, refetch } = usePipelines();
  const [keyword, setKeyword] = useState('');
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerPipeline, setTriggerPipeline] = useState<string | undefined>();

  const pipelines = data?.items ?? [];

  // 前端搜索过滤
  const filtered = useMemo(() => {
    if (!keyword.trim()) return pipelines;
    const kw = keyword.toLowerCase();
    return pipelines.filter(
      (p) => p.name.toLowerCase().includes(kw) || p.file.toLowerCase().includes(kw),
    );
  }, [pipelines, keyword]);

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    {
      title: '文件',
      dataIndex: 'file',
      key: 'file',
      render: (file: string) => <Link to={`/pipelines/${file}`}>{file}</Link>,
    },
    { title: '任务数', dataIndex: 'task_count', key: 'task_count', width: 80 },
    { title: '子流水线数', dataIndex: 'subpipeline_count', key: 'subpipeline_count', width: 100 },
    {
      title: '最近运行',
      key: 'last_run',
      render: (_: unknown, record: PipelineSummary) => {
        if (!record.last_run) return '-';
        return (
          <Space>
            {record.last_run.created_at && dayjs(record.last_run.created_at).format('MM-DD HH:mm')}
            <StatusTag status={record.last_run.status as RunStatus} />
          </Space>
        );
      },
    },
    {
      title: '成功率',
      dataIndex: 'success_rate',
      key: 'success_rate',
      width: 160,
      render: (rate: number) => (
        <Progress percent={Math.round(rate * 100)} size="small" />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, record: PipelineSummary) => (
        <Space>
          <Tooltip title="查看详情">
            <Button type="text" size="small" icon={<Eye size={14} />} onClick={() => navigate(`/pipelines/${record.file}`)} />
          </Tooltip>
          <Tooltip title="触发运行">
            <Button type="text" size="small" icon={<Play size={14} />} onClick={() => { setTriggerPipeline(record.file); setTriggerOpen(true); }} />
          </Tooltip>
          <Tooltip title="导出图片（暂未实现）">
            <Button type="text" size="small" icon={<Image size={14} />} onClick={() => message.info('导出图片功能将在详情页实现')} />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="p-4">
      <Card>
        {/* 工具栏 */}
        <div className="flex justify-between mb-4">
          <Input.Search
            placeholder="搜索流水线名称或文件"
            allowClear
            style={{ width: 300 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            prefix={<Search size={14} />}
          />
          <Space>
            <Button icon={<RefreshCw size={14} />} onClick={() => refetch()}>刷新</Button>
            <Button type="primary" icon={<Play size={14} />} onClick={() => { setTriggerPipeline(undefined); setTriggerOpen(true); }}>触发运行</Button>
          </Space>
        </div>

        {/* 流水线表格 */}
        <Table
          rowKey="file"
          columns={columns}
          dataSource={filtered}
          loading={isLoading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="middle"
        />
      </Card>

      <TriggerRunModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        defaultPipeline={triggerPipeline}
      />
    </div>
  );
}
