import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import { Card, Table, Button, Input, Space, Tooltip, Tag } from 'antd';
import { Search, RefreshCw, Play, ChevronRight, CheckCircle2, AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';
import dayjs from 'dayjs';
import { usePipelines } from '@/api/pipelines';
import StatusTag from '@/components/StatusTag';
import TriggerRunModal from '@/components/TriggerRunModal';
import SuccessRateChart from './components/SuccessRateChart';
import type { PipelineSummary, RunStatus, ValidationError } from '@/types';

/** 行类型 */
type Row =
  | (PipelineSummary & { kind: 'project'; children: Row[]; pipelineCount: number })
  | (PipelineSummary & { kind: 'folder'; children: PipelineSummary[]; pipelineCount: number })
  | (PipelineSummary & { kind: 'pipeline' });

export default function PipelineListPage() {
  const { data, isLoading, refetch } = usePipelines();
  const [keyword, setKeyword] = useState('');
  const [triggerOpen, setTriggerOpen] = useState(false);
  const [triggerDefinitionId, setTriggerDefinitionId] = useState<string | undefined>();
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
            id: '',
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
            // project/folder 行不需要合法性状态，默认 valid
            valid: true,
            validation_error: null,
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
          id: '',
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
          valid: true,
          validation_error: null,
          kind: 'project',
          children,
          pipelineCount,
        });
      }
    }
    return out;
  }, [filtered]);

  const isExpandable = (r: Row) => r.kind === 'project' || r.kind === 'folder';

  /**
   * 统一的行 key 生成。
   * pipeline 使用 record.id（唯一），不能用 record.file — 不同项目下可能有同名文件，
   * 会导致 React key 冲突，使只有最后一个 project 的展开/折叠正常工作。
   * folder 加入 project_id 防止跨项目同名文件夹 key 冲突。
   */
  const getRowKey = useCallback((record: Row): string => {
    if (record.kind === 'project') return `__proj__${record.name}`;
    if (record.kind === 'folder') return `__folder__${record.project_id}__${record.name}`;
    return record.id;
  }, []);

  /**
   * 自定义展开/折叠切换，不依赖 Ant Design 内部状态。
   * 折叠父行时同时清除子行展开状态，防止重新展开时子文件夹自动展开（"展开多出来内容"）。
   */
  const toggleExpand = useCallback((key: string, record?: Row) => {
    setExpandedRowKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
        // 折叠 project 时，清除其下所有 folder 的展开状态
        if (record?.kind === 'project') {
          for (const child of record.children) {
            if (child.kind === 'folder') next.delete(getRowKey(child));
          }
        }
      } else {
        next.add(key);
      }
      return next;
    });
  }, [getRowKey]);

  // 首次加载时按 pipelineCount 决定默认展开（≤10 展开，>10 收起）
  const defaultedRef = useRef(false);
  useEffect(() => {
    if (defaultedRef.current || rows.length === 0) return;
    defaultedRef.current = true;
    const keys = new Set<string>();
    for (const r of rows) {
      if (r.kind === 'project' && (r.pipelineCount ?? 0) <= 10) {
        keys.add(getRowKey(r));
      }
    }
    setExpandedRowKeys(keys);
  }, [rows, getRowKey]);

  const handleOpenTrigger = useCallback((definitionId?: string, projectId?: string | null) => {
    setTriggerDefinitionId(definitionId);
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
            <span style={{ fontWeight: 600, color: '#121620', display: 'inline-flex', alignItems: 'center' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 18, height: 18, borderRadius: 3, background: 'rgba(126, 173, 255, 0.15)',
                color: '#3D5BFF', fontSize: 11, fontWeight: 600, marginRight: 6, flexShrink: 0,
              }}>
                P
              </span>
              {record.name}
              <Tag style={{ marginLeft: 8, fontSize: 11, borderRadius: 3 }}>{record.pipelineCount}</Tag>
            </span>
          );
        }
        if (record.kind === 'folder') {
          return (
            <span style={{ fontWeight: 600, color: '#121620', display: 'inline-flex', alignItems: 'center' }}>
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 18, height: 18, borderRadius: 3, background: 'rgba(124, 127, 136, 0.12)',
                color: '#7C7F88', fontSize: 11, fontWeight: 600, marginRight: 6, flexShrink: 0,
              }}>
                F
              </span>
              {record.name}/
              <Tag style={{ marginLeft: 8, fontSize: 11, borderRadius: 3 }}>{record.pipelineCount}</Tag>
            </span>
          );
        }
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {/* v1 (2026-07): issue #195 — 列表页 YAML 合法性图标 */}
            <Tooltip
              title={
                record.validation_error ? (
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 2 }}>YAML 校验失败</div>
                    <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                      {record.validation_error.path ? `${record.validation_error.path}: ` : ''}
                      {record.validation_error.line != null ? `行 ${record.validation_error.line}` : ''}
                      {record.validation_error.column != null ? `:${record.validation_error.column} ` : ''}
                      — {record.validation_error.message}
                    </div>
                  </div>
                ) : record.valid === false ? (
                  'YAML 校验失败'
                ) : (
                  'YAML 合法'
                )
              }
            >
              <span style={{ display: 'inline-flex', alignItems: 'center' }}>
                {record.valid !== false ? (
                  <CheckCircle2 size={14} color="#52c41a" />
                ) : (
                  <AlertTriangle size={14} color="#ff4d4f" />
                )}
              </span>
            </Tooltip>
            <Link to={record.valid !== false
              ? `/pipelines/${record.project_id}/${encodeURIComponent(record.id)}`
              : `/pipelines/${record.project_id}/_file_/${encodeURIComponent(record.file)}`
            } style={{ fontWeight: 500, color: '#3D5BFF' }}>
              {record.name}
            </Link>
          </span>
        );
      },
    },
    {
      title: '文件',
      key: 'file',
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#7C7F88', fontSize: 12 }}>--</span>;
        return (
          <Link to={record.valid !== false
            ? `/pipelines/${record.project_id}/${encodeURIComponent(record.id)}`
            : `/pipelines/${record.project_id}/_file_/${encodeURIComponent(record.file)}`
          } style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#7C7F88' }}>
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
        if (record.kind !== 'pipeline') return <span style={{ color: '#7C7F88' }}>--</span>;
        if (!record.last_run || !record.last_run.created_at) return '-';
        return dayjs(record.last_run.created_at).format('MM-DD HH:mm');
      },
    },
    {
      title: '最近运行状态',
      key: 'last_run_status',
      width: 100,
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#7C7F88' }}>--</span>;
        if (!record.last_run) return '-';
        return <StatusTag status={record.last_run.status as RunStatus} />;
      },
    },
    {
      title: '成功率',
      key: 'success_rate',
      width: 170,
      render: (_: unknown, record: Row) => {
        if (record.kind !== 'pipeline') return <span style={{ color: '#7C7F88', fontSize: 12 }}>--</span>;
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
              <Button type="text" size="small" icon={<Play size={14} />} onClick={() => handleOpenTrigger(record.id, record.project_id)} />
            </Tooltip>
          </Space>
        );
      },
    },
  ], [handleOpenTrigger]);

  return (
    <div className="p-6 h-full overflow-auto">
      <Card
        style={{
          border: '1px solid #E3E4E8',
          borderRadius: 8,
          boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
        }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          title={() => (
            <div className="flex justify-between items-center px-1">
              <Input
                placeholder="搜索流水线名称或文件"
                allowClear
                style={{ width: 300 }}
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                prefix={<Search size={14} color="#7C7F88" />}
              />
              <Space>
                <Button icon={<RefreshCw size={14} />} onClick={() => refetch()}>刷新</Button>
                <Button type="primary" icon={<Play size={14} />} onClick={() => handleOpenTrigger(undefined)}>触发运行</Button>
              </Space>
            </div>
          )}
          rowKey={getRowKey}
          columns={columns}
          dataSource={rows}
          loading={isLoading}
          pagination={{ pageSize: 50, showSizeChanger: false }}
          size="middle"
          scroll={{ x: 'max-content' }}
          expandable={{
            childrenColumnName: 'children',
            expandedRowKeys: [...expandedRowKeys],
            // onExpandedRowsChange 为 noop：完全由 toggleExpand 控制，不受 Ant Design 内部状态干扰
            onExpandedRowsChange: () => {},
            rowExpandable: isExpandable,
            expandIcon: ({ expanded, record }) => {
              if (!isExpandable(record as Row)) return <span style={{ display: 'inline-block', width: 18 }} />;
              const key = getRowKey(record as Row);
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
                    color: '#7C7F88',
                  }}
                  onClick={(e) => { e.stopPropagation(); toggleExpand(key, record as Row); }}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.currentTarget.click(); } }}
                >
                  <ChevronRight size={14} />
                </span>
              );
            },
            indentSize: 22,
          }}
          onRow={(record: Row) => {
            if (!isExpandable(record)) return {};
            const key = getRowKey(record);
            return {
              style: { cursor: 'pointer' },
              onClick: () => toggleExpand(key, record),
            };
          }}
        />
      </Card>

      <TriggerRunModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        defaultDefinitionId={triggerDefinitionId}
        defaultProjectId={triggerProjectId}
      />

      {/* Issue #104: 展开/折叠动画样式 */}
      <style>{`
        .pipeline-expand-icon:hover {
          background: rgba(126, 173, 255, 0.15);
          color: #3D5BFF;
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
