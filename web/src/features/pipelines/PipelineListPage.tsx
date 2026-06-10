import { useState, useMemo, useCallback } from 'react';
import { Card, Table, Button, Input, Space, Progress, Tooltip, message, Tag } from 'antd';
import { Search, RefreshCw, Play, Eye, Image, Folder, FolderOpen, ChevronRight, ChevronDown } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import { usePipelines } from '@/api/pipelines';
import StatusTag from '@/components/StatusTag';
import TriggerRunModal from '@/components/TriggerRunModal';
import type { PipelineSummary, RunStatus } from '@/types';

/** 表格行类型：folder 虚拟行 or pipeline 真实行 */
type Row =
  | (PipelineSummary & { isFolder: true; children: PipelineSummary[]; pipelineCount: number })
  | (PipelineSummary & { isFolder: false; children?: undefined });

export default function PipelineListPage() {
  const navigate = useNavigate();
  const { data, isLoading, refetch } = usePipelines();
  const [keyword, setKeyword] = useState('');
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerPipeline, setTriggerPipeline] = useState<string | undefined>();
  const [triggerProjectId, setTriggerProjectId] = useState<string | null>(null);

  // 前端搜索过滤
  const filtered = useMemo(() => {
    const list = data?.items ?? [];
    if (!keyword.trim()) return list;
    const kw = keyword.toLowerCase();
    return list.filter(
      (p) => p.name.toLowerCase().includes(kw) || p.file.toLowerCase().includes(kw),
    );
  }, [data?.items, keyword]);

  // 按 folder 分组：folder=="" 走根分组"/"，folder 走对应名字
  // 返回 Row[]：folder 行（可展开）+ 根目录 pipeline 行
  const rows = useMemo<Row[]>(() => {
    const groups = new Map<string, PipelineSummary[]>();
    for (const p of filtered) {
      const key = p.folder || '';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(p);
    }
    const out: Row[] = [];
    // 先根目录（folder==""）
    if (groups.has('')) {
      for (const p of groups.get('')!) {
        out.push({ ...p, isFolder: false });
      }
    }
    // 再子文件夹（按字母序）
    const subFolders = [...groups.keys()].filter((k) => k !== '').sort();
    for (const folder of subFolders) {
      const children = groups.get(folder)!;
      out.push({
        // 虚拟 folder 行
        name: folder,
        file: '',
        folder,
        project_id: null,
        task_count: children.reduce((s, c) => s + c.task_count, 0),
        subpipeline_count: children.reduce((s, c) => s + c.subpipeline_count, 0),
        last_run: null,
        success_rate:
          children.reduce((s, c) => s + c.success_rate, 0) / Math.max(children.length, 1),
        isFolder: true,
        children,
        pipelineCount: children.length,
      });
    }
    return out;
  }, [filtered]);

  // 稳定化回调：避免 Table 每次输入都重新渲染
  const handleOpenDetail = useCallback(
    (file: string) => navigate(`/pipelines/${encodeURIComponent(file)}`),
    [navigate],
  );
  const handleOpenTrigger = useCallback((file?: string, projectId?: string | null) => {
    setTriggerPipeline(file);
    setTriggerProjectId(projectId ?? null);
    setTriggerOpen(true);
  }, []);
  const handleExportImage = useCallback(() => {
    message.info('导出图片功能将在详情页实现');
  }, []);

  const columns = useMemo(() => [
    {
      title: '名称',
      key: 'name',
      render: (_: unknown, record: Row) => {
        if (record.isFolder) {
          return (
            <span style={{ fontWeight: 600, color: '#1f2937' }}>
              <FolderOpen size={14} style={{ marginRight: 6, color: '#f59e0b' }} />
              {record.name}/
              <Tag style={{ marginLeft: 8 }}>{record.pipelineCount} 个</Tag>
            </span>
          );
        }
        return <span style={{ fontWeight: 500 }}>{record.name}</span>;
      },
    },
    {
      title: '文件',
      key: 'file',
      render: (_: unknown, record: Row) => {
        if (record.isFolder) return <span style={{ color: '#9ca3af', fontSize: 12 }}>—</span>;
        return (
          <Link to={`/pipelines/${encodeURIComponent(record.file)}`} style={{ fontFamily: 'monospace', fontSize: 12 }}>
            {record.file}
          </Link>
        );
      },
    },
    {
      title: '项目',
      key: 'project_id',
      width: 110,
      render: (_: unknown, record: Row) => {
        if (record.isFolder) return <span style={{ color: '#9ca3af', fontSize: 12 }}>—</span>;
        return record.project_id ? (
          <Tag style={{ fontFamily: 'monospace', fontSize: 11 }}>{record.project_id}</Tag>
        ) : (
          <span style={{ color: '#9ca3af', fontSize: 12 }}>默认</span>
        );
      },
    },
    {
      title: '任务数',
      key: 'task_count',
      width: 80,
      render: (_: unknown, r: Row) => r.task_count,
    },
    {
      title: '子流水线数',
      key: 'subpipeline_count',
      width: 100,
      render: (_: unknown, r: Row) => r.subpipeline_count,
    },
    {
      title: '最近运行',
      key: 'last_run',
      render: (_: unknown, record: Row) => {
        if (record.isFolder) return <span style={{ color: '#9ca3af' }}>—</span>;
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
      key: 'success_rate',
      width: 160,
      render: (_: unknown, record: Row) => (
        <Progress percent={Math.round((record.success_rate || 0))} size="small" />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_: unknown, record: Row) => {
        if (record.isFolder) return null;
        return (
          <Space>
            <Tooltip title="查看详情">
              <Button type="text" size="small" icon={<Eye size={14} />} onClick={() => handleOpenDetail(record.file)} />
            </Tooltip>
            <Tooltip title="触发运行">
              <Button type="text" size="small" icon={<Play size={14} />} onClick={() => handleOpenTrigger(record.file, record.project_id)} />
            </Tooltip>
            <Tooltip title="导出图片（暂未实现）">
              <Button type="text" size="small" icon={<Image size={14} />} onClick={handleExportImage} />
            </Tooltip>
          </Space>
        );
      },
    },
  ], [handleOpenDetail, handleOpenTrigger, handleExportImage]);

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
            <Button type="primary" icon={<Play size={14} />} onClick={() => handleOpenTrigger(undefined)}>触发运行</Button>
          </Space>
        </div>

        {/* 流水线表格（按文件夹分组） */}
        <Table
          rowKey={(record: Row) => (record.isFolder ? `__folder__${record.name}` : record.file)}
          columns={columns}
          dataSource={rows}
          loading={isLoading}
          pagination={{ pageSize: 50, showSizeChanger: false }}
          size="middle"
          expandable={{
            childrenColumnName: 'children',
            defaultExpandAllRows: false,
            rowExpandable: (record) => (record as Row).isFolder === true,
            expandIcon: ({ expanded, onExpand, record }) => {
              const r = record as Row;
              if (!r.isFolder) return <span style={{ width: 16, display: 'inline-block' }} />;
              return (
                <Button
                  type="text"
                  size="small"
                  icon={expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  onClick={(e) => {
                    e.stopPropagation();
                    onExpand(record, e as React.MouseEvent<HTMLElement>);
                  }}
                  style={{ width: 24, height: 24, padding: 0 }}
                />
              );
            },
          }}
          rowClassName={(record: Row) => (record.isFolder ? 'pipeline-folder-row' : '')}
        />
      </Card>

      <TriggerRunModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        defaultPipeline={triggerPipeline}
        defaultProjectId={triggerProjectId}
      />
    </div>
  );
}
