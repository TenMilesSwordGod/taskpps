import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Card, Table, Button, Input, Space, Tooltip, Tag } from 'antd';
import { Search, RefreshCw, Play, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import dayjs from 'dayjs';
import { usePipelines } from '@/api/pipelines';
import StatusTag from '@/components/StatusTag';
import TriggerRunModal from '@/components/TriggerRunModal';
import SuccessRateChart from './components/SuccessRateChart';
import type { PipelineSummary, RunStatus } from '@/types';

/** 行类型 */
type Row =
  | (PipelineSummary & { kind: 'project'; children: Row[]; pipelineCount: number })
  | (PipelineSummary & { kind: 'folder'; children: PipelineSummary[]; pipelineCount: number })
  | (PipelineSummary & { kind: 'pipeline' });

export default function PipelineListPage() {
  const { data, isLoading, refetch } = usePipelines();
  const [keyword, setKeyword] = useState('');
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerPipeline, setTriggerPipeline] = useState<string | undefined>();
  const [triggerProjectId, setTriggerProjectId] = useState<string | null>(null);
  const [expandedRowKeys, setExpandedRowKeys] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const list = data?.items ?? [];
    if (!keyword.trim()) return list;
    const kw = keyword.toLowerCase();
    return list.filter(
      (p) => p.name.toLowerCase().includes(kw) || p.file.toLowerCase().includes(kw),
    );
  }, [data?.items, keyword]);

  // 按 project -> folder 两级分组
  const rows = useMemo<Row[]>(() => {
    // 先按 project 分组
    const projectGroups = new Map<string, PipelineSummary[]>();
    for (const p of filtered) {
      const pid = p.project_id || '__default__';
      if (!projectGroups.has(pid)) projectGroups.set(pid, []);
      projectGroups.get(pid)!.push(p);
    }

    const out: Row[] = [];
    const sortedProjects = [...projectGroups.keys()].sort();

    for (const pid of sortedProjects) {
      const projectPipelines = projectGroups.get(pid)!;
      // Issue #184: 折叠行显示 project_name 而非 project_id
      const projectName = projectPipelines[0]?.project_name || pid;
      const projectLabel = pid === '__default__' ? '' : projectName;

      // 在 project 内按 folder 分组
      const folderGroups = new Map<string, PipelineSummary[]>();
      for (const p of projectPipelines) {
        const folder = p.folder || '';
        if (!folderGroups.has(folder)) folderGroups.set(folder, []);
        folderGroups.get(folder)!.push(p);
      }

      const children: Row[] = [];
      const sortedFolders = [...folderGroups.keys()].sort();

      for (const folder of sortedFolders) {
        const folderPipelines = folderGroups.get(folder)!;
        if (folder === '') {
          // 无 folder 的 pipeline 直接放在 project 下
          for (const p of folderPipelines) {
            children.push({ ...p, kind: 'pipeline' as const });
          }
        } else {
          children.push({
            name: folder,
            file: '',
            folder,
            project_id: pid === '__default__' ? null : pid,
            project_name: null,
            task_count: folderPipelines.reduce((s, c) => s + c.task_count, 0),
            subpipeline_count: folderPipelines.reduce((s, c) => s + c.subpipeline_count, 0),
            last_run: null,
            success_rate:
              folderPipelines.reduce((s, c) => s + c.success_rate, 0) / Math.max(folderPipelines.length, 1),
            recent_runs: [],
            kind: 'folder',
            children: folderPipelines.map((p) => ({ ...p, kind: 'pipeline' as const })),
            pipelineCount: folderPipelines.length,
          });
        }
      }

      const pipelineCount = children.filter((c) => c.kind === 'pipeline').length
        + children.filter((c) => c.kind === 'folder').length;

      // 单项目无 folder 时不要 project 包裹层
      if (sortedProjects.length === 1 && !projectLabel) {
        out.push(...children);
      } else {
        out.push({
          name: projectLabel || '(default)',
          file: '',
          folder: '',
          project_id: pid === '__default__' ? null : pid,
          project_name: projectName,
          task_count: projectPipelines.reduce((s, c) => s + c.task_count, 0),
          subpipeline_count: projectPipelines.reduce((s, c) => s + c.subpipeline_count, 0),
          last_run: null,
          success_rate: projectPipelines.length > 0
            ? projectPipelines.reduce((s, c) => s + c.success_rate, 0) / projectPipelines.length
            : 0,
          recent_runs: [],
          kind: 'project',
          children,
          pipelineCount,
        });
      }
    }
    return out;
  }, [filtered]);

  const isExpandable = (r: Row) => r.kind === 'project' || r.kind === 'folder';

  // 首次加载时按 pipelineCount 决定默认展开（≤10 展开，>10 收起）
  const defaultedRef = useRef(false);
  useEffect(() => {
    if (defaultedRef.current || rows.length === 0) return;
    defaultedRef.current = true;
    const keys = new Set<string>();
    for (const r of rows) {
      if (r.kind === 'project' && (r.pipelineCount ?? 0) <= 10) {
        keys.add(`__proj__${r.name}`);
      }
    }
    setExpandedRowKeys(keys);
  }, [rows]);

  const handleOpenTrigger = useCallback((file?: string, projectId?: string | null) => {
    setTriggerPipeline(file);
    setTriggerProjectId(projectId ?? null);
    setTriggerOpen(true);
  }, []);

  const columns = useMemo(() => [
    {
      title: '名称',
      key: 'name',
      render: (_: unknown, record: Row) => {
        if (record.kind === 'project') {
          return (
            <span style={{ fontWeight: 600, color: '#1f2937', display: 'inline-flex', alignItems: 'center' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 18, height: 18, borderRadius: 4, background: '#3b82f6' + '18',
                color: '#3b82f6', fontSize: 11, fontWeight: 600, marginRight: 6, flexShrink: 0,
              }}>
                P
              </span>
              {record.name}
              <Tag style={{ marginLeft: 8, fontSize: 11 }}>{record.pipelineCount}</Tag>
            </span>
          );
        }
        if (record.kind === 'folder') {
          return (
            <span style={{ fontWeight: 600, color: '#1f2937', display: 'inline-flex', alignItems: 'center' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 18, height: 18, borderRadius: 4, background: '#f59e0b' + '18',
                color: '#d97706', fontSize: 11, fontWeight: 600, marginRight: 6, flexShrink: 0,
              }}>
                F
              </span>
              {record.name}/
              <Tag style={{ marginLeft: 8, fontSize: 11 }}>{record.pipelineCount}</Tag>
            </span>
          );
        }
        return (
          <Link to={`/pipelines/${encodeURIComponent(record.file)}`} style={{ fontWeight: 500, color: '#3b82f6' }}>
            {record.name}
          </Link>
        );
      },
    },
    {
      title: '文件',
      key: 'file',
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#9ca3af', fontSize: 12 }}>--</span>;
        return (
          <Link to={`/pipelines/${encodeURIComponent(record.file)}`} style={{ fontFamily: 'monospace', fontSize: 12 }}>
            {record.file}
          </Link>
        );
      },
    },
    {
      title: '任务',
      key: 'task_count',
      width: 60,
      render: (_: unknown, r: Row) => r.task_count,
    },
    {
      title: '子流水线',
      key: 'subpipeline_count',
      width: 80,
      render: (_: unknown, r: Row) => r.subpipeline_count,
    },
    {
      title: '最近运行时间',
      key: 'last_run_time',
      width: 120,
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#9ca3af' }}>--</span>;
        if (!record.last_run || !record.last_run.created_at) return '-';
        return dayjs(record.last_run.created_at).format('MM-DD HH:mm');
      },
    },
    {
      title: '最近运行状态',
      key: 'last_run_status',
      width: 100,
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#9ca3af' }}>--</span>;
        if (!record.last_run) return '-';
        return <StatusTag status={record.last_run.status as RunStatus} />;
      },
    },
    {
      title: '成功率',
      key: 'success_rate',
      width: 170,
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#9ca3af', fontSize: 12 }}>--</span>;
        return <SuccessRateChart runs={record.recent_runs || []} />;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return null;
        return (
          <Space>
            <Tooltip title="触发运行">
              <Button type="text" size="small" icon={<Play size={14} />} onClick={() => handleOpenTrigger(record.file, record.project_id)} />
            </Tooltip>
          </Space>
        );
      },
    },
  ], [handleOpenTrigger]);

  return (
    <div className="p-4">
      <Card>
        <Table
          title={() => (
            <div className="flex justify-between items-center">
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
          )}
          rowKey={(record: Row) =>
            record.kind === 'project' ? `__proj__${record.name}`
              : record.kind === 'folder' ? `__folder__${record.name}`
              : record.file
          }
          columns={columns}
          dataSource={rows}
          loading={isLoading}
          pagination={{ pageSize: 50, showSizeChanger: false }}
          size="middle"
          scroll={{ x: 'max-content' }}
          expandable={{
            childrenColumnName: 'children',
            expandedRowKeys: [...expandedRowKeys],
            onExpandedRowsChange: (keys) => {
              setExpandedRowKeys(new Set(keys as string[]));
            },
            defaultExpandAllRows: true,
            rowExpandable: isExpandable,
            expandIcon: ({ expanded, record }) => {
              if (!isExpandable(record as Row)) return <span style={{ display: 'inline-block', width: 18 }} />;
              const key = (record as Row).kind === 'project' ? `__proj__${(record as Row).name}`
                : `__folder__${(record as Row).name}`;
              const handleToggle = () => {
                setExpandedRowKeys((prev) => {
                  const next = new Set(prev);
                  if (next.has(key)) next.delete(key); else next.add(key);
                  return next;
                });
              };
              return (
                <span
                  role="button"
                  tabIndex={0}
                  className="pipeline-expand-icon"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 18,
                    height: 18,
                    borderRadius: 4,
                    cursor: 'pointer',
                    transition: 'transform 200ms ease-out, background 150ms ease-out',
                    transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    color: '#6b7280',
                  }}
                  onClick={(e) => { e.stopPropagation(); handleToggle(); }}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleToggle(); } }}
                >
                  <ChevronRight size={14} />
                </span>
              );
            },
            indentSize: 22,
          }}
          onRow={(record: Row) => {
            if (!isExpandable(record)) return {};
            const key = record.kind === 'project' ? `__proj__${record.name}`
              : `__folder__${record.name}`;
            return {
              style: { cursor: 'pointer' },
              onClick: () => {
                setExpandedRowKeys((prev) => {
                  const next = new Set(prev);
                  if (next.has(key)) next.delete(key); else next.add(key);
                  return next;
                });
              },
            };
          }}
        />
      </Card>

      <TriggerRunModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        defaultPipeline={triggerPipeline}
        defaultProjectId={triggerProjectId}
      />

      {/* Issue #104: 展开/折叠动画样式 */}
      <style>{`
        .pipeline-expand-icon:hover {
          background: rgba(59, 130, 246, 0.1);
          color: #3b82f6;
        }
        .ant-table-expanded-row > td {
          padding-top: 0 !important;
          padding-bottom: 0 !important;
        }
        .ant-table-expanded-row .ant-table-row {
          animation: pipelineRowFadeIn 200ms ease-out;
        }
        @keyframes pipelineRowFadeIn {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .pipeline-expand-icon { transition: none !important; }
          .ant-table-expanded-row .ant-table-row { animation: none !important; }
        }
      `}</style>
    </div>
  );
}
