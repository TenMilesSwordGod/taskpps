import { useMemo } from 'react';
import { Tree, Tooltip, Tag, Spin } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { PartitionOutlined, AppstoreOutlined } from '@ant-design/icons';
import { AlertCircle, CheckCircle2, Clock, Bug, FileText, Terminal } from 'lucide-react';
import StatusTag from '@/components/StatusTag';
import { useRunConsole } from '@/api/runs';
import type { PipelineDetail, TaskStatus, SubPipeline, TaskYAML } from '@/types';

interface TaskRunInfo {
  task_name: string;
  status: TaskStatus;
  exit_code: number | null;
  started_at: string | null;
  finished_at: string | null;
}

interface TaskTreeProps {
  pipeline: PipelineDetail;
  taskStatuses?: Record<string, TaskStatus>;
  taskRuns?: TaskRunInfo[];
  selectedTaskId?: string;
  onSelect: (taskId: string | null) => void;
  /** 是否展示 system debug log */
  debugVisible?: boolean;
  /** run ID（用于拉取 console.log） */
  runId?: string;
}

/** 推断任务类型 */
function inferTaskType(task: TaskYAML): 'command' | 'invoke' | 'steps' | 'git' | 'nexus' {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

const TYPE_LABEL: Record<string, string> = {
  command: 'CMD', invoke: 'INV', steps: 'STP', git: 'GIT', nexus: 'NEX',
};

const TYPE_COLOR: Record<string, string> = {
  command: '#6b7280', invoke: '#3b82f6', steps: '#8b5cf6', git: '#f59e0b', nexus: '#06b6d4',
};

function fmtDur(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  if (m > 0) return `${m}m${s % 60}s`;
  return `${s}s`;
}

type LogLevel = 'error' | 'warn' | 'info' | 'debug' | 'unknown';

function detectLevel(line: string): LogLevel {
  if (/\[ERROR\]|\[FATAL\]|Traceback|Error:/i.test(line)) return 'error';
  if (/\[WARN\]/i.test(line)) return 'warn';
  if (/\[DEBUG\]/i.test(line)) return 'debug';
  if (/\[INFO\]/i.test(line)) return 'info';
  return 'unknown';
}

const LEVEL_CFG: Record<LogLevel, { color: string; bg: string; short: string }> = {
  error: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', short: 'ERR' },
  warn: { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', short: 'WRN' },
  info: { color: '#3b82f6', bg: 'transparent', short: 'INF' },
  debug: { color: '#9ca3af', bg: 'transparent', short: 'DBG' },
  unknown: { color: '#6b7280', bg: 'transparent', short: 'LOG' },
};

function parseExitCodes(content: string) {
  const codes: { taskName: string; code: number }[] = [];
  for (const line of content.split('\n')) {
    const m = line.match(/\[([^\]]+)\]\s*(?:.*?exit[:-]?\s*code[:=]?\s*|exit_code[:=]?\s*)(-?\d+)/i);
    if (m) codes.push({ taskName: m[1], code: parseInt(m[2]) });
  }
  return codes;
}

/** 紧凑层级任务树 + 可选 system debug log */
export default function TaskTree({ pipeline, taskStatuses, taskRuns, selectedTaskId, onSelect, debugVisible, runId }: TaskTreeProps) {
  const runMap = useMemo(() => {
    if (!taskRuns) return new Map<string, TaskRunInfo>();
    const m = new Map<string, TaskRunInfo>();
    for (const r of taskRuns) m.set(r.task_name, r);
    return m;
  }, [taskRuns]);

  // 拉取 console.log（仅 debugVisible 且 runId 存在时）
  const { data: consoleData, isLoading: consoleLoading } = useRunConsole(
    debugVisible && runId ? runId : undefined,
    500,
  );

  const treeData = useMemo<DataNode[]>(() => {
    const subpipelines: SubPipeline[] = pipeline.pipelines || [];
    const nodes: DataNode[] = subpipelines.map((sub) => {
      const children: DataNode[] = sub.tasks.map((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];
        const run = runMap.get(taskId);
        const type = inferTaskType(task);

        let durStr: string | null = null;
        if (run?.started_at && run?.finished_at) {
          const dur = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
          durStr = fmtDur(Math.max(0, dur));
        } else if (run?.started_at && !run?.finished_at) {
          durStr = '…';
        }

        const isSelected = selectedTaskId === taskId;
        const exitOk = run?.exit_code === 0;
        const exitBad = run?.exit_code != null && run.exit_code !== 0;

        return {
          key: taskId,
          title: (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', minWidth: 0, whiteSpace: 'nowrap' }}>
              <Tooltip title={type}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 18, fontSize: 10, fontWeight: 600, borderRadius: 4, background: TYPE_COLOR[type] + '18', color: TYPE_COLOR[type], flexShrink: 0 }}>
                  {TYPE_LABEL[type]}
                </span>
              </Tooltip>
              <span style={{ fontSize: 13, fontWeight: isSelected ? 600 : 400, color: isSelected ? '#1d4ed8' : '#374151', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>
                {task.name}
              </span>
              <span style={{ flex: 1 }} />
              {durStr && (
                <Tooltip title={run?.started_at ? `开始: ${new Date(run.started_at).toLocaleString('zh-CN')}` : ''}>
                  <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                    <Clock size={10} />{durStr}
                  </span>
                </Tooltip>
              )}
              {exitOk && (
                <Tooltip title="Exit 0 — 成功">
                  <span style={{ fontSize: 11, color: '#10b981', fontWeight: 500, flexShrink: 0 }}>
                    <CheckCircle2 size={10} style={{ verticalAlign: -1, marginRight: 2 }} />0
                  </span>
                </Tooltip>
              )}
              {exitBad && (
                <Tooltip title={`Exit ${run!.exit_code} — 失败`}>
                  <span style={{ fontSize: 11, color: '#ef4444', fontWeight: 500, flexShrink: 0 }}>
                    <AlertCircle size={10} style={{ verticalAlign: -1, marginRight: 2 }} />{run!.exit_code}
                  </span>
                </Tooltip>
              )}
              {status && <StatusTag status={status} />}
            </div>
          ),
        };
      });

      return {
        key: `sub-${sub.name}`,
        title: (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', whiteSpace: 'nowrap' }}>
            <PartitionOutlined style={{ color: '#8b5cf6', flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{sub.name}</span>
            <span style={{ flex: 1, minWidth: 4 }} />
            <Tooltip title={`${sub.tasks.length} 个任务`}>
              <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 20, height: 20, fontSize: 11, fontWeight: 600, borderRadius: 6, padding: '0 6px', background: '#8b5cf6' + '14', color: '#8b5cf6', flexShrink: 0 }}>
                {sub.tasks.length}
              </span>
            </Tooltip>
          </div>
        ),
        children,
      };
    });

    // System Log 节点（当 debugVisible 且有 console data 时）
    if (debugVisible && runId) {
      const content = consoleData?.content;
      const logLines = content ? content.split('\n') : [];
      const exitCodes = content ? parseExitCodes(content) : [];
      const errorCount = logLines.filter((l) => detectLevel(l) === 'error').length;

      const logChildren: DataNode[] = logLines.slice(0, 200).map((line, i) => {
        const level = detectLevel(line);
        const cfg = LEVEL_CFG[level];
        return {
          key: `__log__${i}`,
          title: (
            <div style={{ display: 'flex', gap: 6, padding: '1px 0', fontSize: 11, fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              <span style={{ color: cfg.color, fontWeight: 600, flexShrink: 0, minWidth: 28 }}>{cfg.short}</span>
              <span style={{ color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis' }}>{line}</span>
            </div>
          ),
        };
      });

      nodes.push({
        key: '__debug__',
        title: (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', whiteSpace: 'nowrap' }}>
            <Bug size={14} color="#f59e0b" style={{ flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>System Log</span>
            {consoleLoading ? (
              <Spin size="small" />
            ) : consoleData?.exists ? (
              <>
                <Tag color="default" style={{ margin: 0, padding: '0 6px', fontSize: 10, lineHeight: '16px', height: 18 }}>
                  <FileText size={10} style={{ marginRight: 2 }} />{consoleData.lines} 行
                </Tag>
                {errorCount > 0 && (
                  <Tag color="error" style={{ margin: 0, padding: '0 6px', fontSize: 10, lineHeight: '16px', height: 18 }}>
                    <AlertCircle size={10} style={{ marginRight: 2 }} />{errorCount}
                  </Tag>
                )}
                {exitCodes.map((ec) => (
                  <Tag key={ec.taskName} color={ec.code === 0 ? 'success' : 'error'} style={{ margin: 0, padding: '0 6px', fontSize: 10, lineHeight: '16px', height: 18 }}>
                    {ec.taskName.split('.').pop()}:{ec.code}
                  </Tag>
                ))}
              </>
            ) : (
              <Tag color="default" style={{ margin: 0, padding: '0 6px', fontSize: 10, lineHeight: '16px', height: 18 }}>
                <Terminal size={10} style={{ marginRight: 2 }} />无文件
              </Tag>
            )}
          </div>
        ),
        children: logChildren.length > 0 ? logChildren : undefined,
      });
    }

    return nodes;
  }, [pipeline, taskStatuses, runMap, selectedTaskId, debugVisible, runId, consoleData, consoleLoading]);

  const selectedKeys = selectedTaskId ? [selectedTaskId] : [];

  return (
    <div style={{ height: '100%', overflow: 'auto', background: '#fafafa', borderRight: '1px solid #e5e7eb' }}>
      <div className="px-3 py-2 border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <AppstoreOutlined style={{ color: '#3b82f6', flexShrink: 0 }} />
          <span className="text-sm font-medium truncate">{pipeline.name}</span>
        </div>
      </div>
      <Tree
        treeData={treeData}
        defaultExpandAll
        selectedKeys={selectedKeys}
        onSelect={(keys) => {
          const key = keys[0] as string | undefined;
          if (key && (key.startsWith('sub-') || key.startsWith('__'))) return;
          onSelect(key ?? null);
        }}
        blockNode
        style={{ padding: '6px 0' }}
      />
    </div>
  );
}
