import { useMemo, useState, useEffect } from 'react';
import { Tree, Tooltip, Dropdown } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { PartitionOutlined, AppstoreOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { Loader2, RotateCcw, History } from 'lucide-react';

import { useRunConsole } from '@/api/runs';
import type { PipelineDetail, TaskStatus, SubPipeline, TaskYAML } from '@/types';

/** 呼吸灯动画 keyframes */
const BREATHING_STYLE = `
@keyframes breathing {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(59,130,246,0.4); }
  50% { opacity: 0.85; box-shadow: 0 0 0 3px rgba(59,130,246,0); }
}
@media (prefers-reduced-motion: reduce) {
  .breathing-badge { animation: none !important; }
}
`;

interface TaskRunInfo {
  task_name: string;
  status: TaskStatus;
  exit_code: number | null;
  error?: string | null;
  started_at: string | null;
  finished_at: string | null;
  /** 服务端计算的耗时（毫秒） */
  duration_ms: number | null;
}

interface TaskTreeProps {
  pipeline: PipelineDetail;
  taskRuns?: TaskRunInfo[];
  selectedTaskId?: string;
  onSelect: (taskId: string | null) => void;
  /** 是否展示 system debug log */
  debugVisible?: boolean;
  /** run ID（用于拉取 console.log） */
  runId?: string;
  /** 是否为运行中状态（启用实时计时器） */
  isLive?: boolean;
  /** SSE 推送的任务状态映射（task_name -> latest status） */
  taskStatusMap?: Record<string, TaskStatus>;
  /** Issue #72: 右键重试回调 */
  onRetry?: (taskName: string) => void;
  /** Issue #72: 查看重试版本回调 */
  onShowVersions?: (taskName: string) => void;
  /** Issue #72: 各任务的重试版本数映射 */
  retryCounts?: Record<string, number>;
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

interface PhaseGroup {
  scope: 'pipeline' | 'sub' | 'task';
  name: string;
  phase: 'setup' | 'teardown';
  lines: string[];
}

function parsePhaseGroups(content: string): PhaseGroup[] {
  const groups: PhaseGroup[] = [];
  const lines = content.split('\n');

  const phasePattern = /^\[(PIPELINE:SETUP|PIPELINE:TEARDOWN|SUB:([^:]+):SETUP|SUB:([^:]+):TEARDOWN|TASK:([^:]+):SETUP|TASK:([^:]+):TEARDOWN)\]/;

  let currentGroup: PhaseGroup | null = null;

  for (const line of lines) {
    const match = line.match(phasePattern);
    if (match) {
      const tag = match[1];
      if (tag === 'PIPELINE:SETUP') {
        currentGroup = { scope: 'pipeline', name: 'pipeline', phase: 'setup', lines: [] };
      } else if (tag === 'PIPELINE:TEARDOWN') {
        currentGroup = { scope: 'pipeline', name: 'pipeline', phase: 'teardown', lines: [] };
      } else if (tag.startsWith('SUB:')) {
        const parts = tag.split(':');
        currentGroup = { scope: 'sub', name: parts[1], phase: parts[2].toLowerCase() as 'setup' | 'teardown', lines: [] };
      } else if (tag.startsWith('TASK:')) {
        const rest = tag.slice(5);
        const lastColon = rest.lastIndexOf(':');
        const name = rest.slice(0, lastColon);
        const phase = rest.slice(lastColon + 1).toLowerCase() as 'setup' | 'teardown';
        currentGroup = { scope: 'task', name, phase, lines: [] };
      }
      if (currentGroup) groups.push(currentGroup);
    } else if (currentGroup) {
      currentGroup.lines.push(line);
    }
  }

  return groups;
}

const PHASE_BADGE: Record<'setup' | 'teardown', { bg: string; color: string; label: string }> = {
  setup: { bg: 'rgba(59,130,246,0.12)', color: '#3b82f6', label: 'SETUP' },
  teardown: { bg: 'rgba(107,114,128,0.12)', color: '#6b7280', label: 'TEAR' },
};

/** 紧凑层级任务树 + 可选 system debug log */
export default function TaskTree({ pipeline, taskRuns, selectedTaskId, onSelect, debugVisible, runId, isLive, taskStatusMap, onRetry, onShowVersions, retryCounts }: TaskTreeProps) {
  // SSE 状态更新：合并到 taskRuns 中
  // Issue #61: 防止陈旧的 SSE 状态覆盖服务端更新的终态状态
  // （SSE 断连重连期间 taskStatusMap 可能停留在旧的 running，而服务端已 failed）
  const liveTaskRuns = useMemo(() => {
    if (!taskStatusMap || !Object.keys(taskStatusMap).length || !taskRuns) return taskRuns;
    return taskRuns.map((r) => {
      const newStatus = taskStatusMap[r.task_name];
      if (!newStatus || newStatus === r.status) return r;
      // Issue #99: 服务端已是终态时，不回退到任何 SSE 状态（含过期的终态），
      // 避免手动切换最终版本后，陈旧 SSE 仍覆盖任务树状态。
      const terminal: Record<string, boolean> = { success: true, failed: true, skipped: true, cancelled: true };
      if (terminal[r.status]) return r;
      return { ...r, status: newStatus };
    });
  }, [taskRuns, taskStatusMap]);

  const runMap = useMemo(() => {
    const runs = liveTaskRuns ?? taskRuns;
    if (!runs) return new Map<string, TaskRunInfo>();
    const m = new Map<string, TaskRunInfo>();
    for (const r of runs) m.set(r.task_name, r);
    return m;
  }, [liveTaskRuns, taskRuns]);

  // 拉取 console.log（仅 debugVisible 且 runId 存在时）
  const { data: consoleData } = useRunConsole(
    debugVisible && runId ? runId : undefined,
    500,
  );

  // 解析 phase groups
  const phaseGroups = useMemo(() => {
    if (!debugVisible || !consoleData?.content) return [];
    return parsePhaseGroups(consoleData.content);
  }, [debugVisible, consoleData?.content]);

  // 受控展开状态
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);

  useEffect(() => {
    const keys: React.Key[] = [];
    for (const sub of pipeline.pipelines || []) {
      keys.push(`sub-${sub.name}`);
    }
    setExpandedKeys(keys);
  }, [pipeline]);

  const treeData = useMemo<DataNode[]>(() => {
    const subpipelines: SubPipeline[] = pipeline.pipelines || [];

    // Helper: build log line children for a phase group
    const buildLogLineNodes = (group: PhaseGroup): DataNode[] =>
      group.lines.map((line, i) => {
        const level = detectLevel(line);
        const cfg = LEVEL_CFG[level];
        return {
          key: `__phase__${group.scope}__${group.name}__${group.phase}__${i}`,
          title: (
            <div style={{ display: 'flex', gap: 6, padding: '1px 0', fontSize: 11, fontFamily: 'monospace', overflow: 'hidden' }}>
              <div style={{ color: cfg.color, fontWeight: 600, flexShrink: 0, minWidth: 28 }}>{cfg.short}</div>
              <div style={{ color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{line}</div>
            </div>
          ),
        };
      });

    // Helper: build a SETUP/TEARDOWN phase node
    const buildPhaseNode = (group: PhaseGroup): DataNode => {
      const badge = PHASE_BADGE[group.phase];
      const scopeLabel = group.scope === 'pipeline' ? 'pipeline' : group.name;
      return {
        key: `__phase__${group.scope}__${group.name}__${group.phase}`,
        title: (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', minWidth: 0, whiteSpace: 'nowrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', height: 18, fontSize: 10, fontWeight: 600, borderRadius: 4, background: badge.bg, color: badge.color, flexShrink: 0, padding: '0 5px' }}>
              {badge.label}
            </span>
            <span style={{ fontSize: 12, color: '#6b7280' }}>{scopeLabel} {group.phase}</span>
          </div>
        ),
        children: group.lines.length > 0 ? buildLogLineNodes(group) : undefined,
      };
    };

    // Lookup helpers for phase groups
    const pipelinePhases = phaseGroups.filter((g) => g.scope === 'pipeline');
    const subPhaseMap = new Map<string, PhaseGroup[]>();
    const taskPhaseMap = new Map<string, PhaseGroup[]>();
    for (const g of phaseGroups) {
      if (g.scope === 'sub') {
        const arr = subPhaseMap.get(g.name) || [];
        arr.push(g);
        subPhaseMap.set(g.name, arr);
      } else if (g.scope === 'task') {
        const arr = taskPhaseMap.get(g.name) || [];
        arr.push(g);
        taskPhaseMap.set(g.name, arr);
      }
    }

    const nodes: DataNode[] = subpipelines.map((sub) => {
      const subKey = `sub-${sub.name}`;
      const subSetup = subPhaseMap.get(sub.name)?.filter((g) => g.phase === 'setup') || [];
      const subTeardown = subPhaseMap.get(sub.name)?.filter((g) => g.phase === 'teardown') || [];

      const taskNodes: DataNode[] = sub.tasks.map((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const run = runMap.get(taskId);
        const type = inferTaskType(task);
        const isRunning = run?.status === 'running';

        let durStr: string | null = null;
        if (run?.duration_ms != null && run.duration_ms >= 0) {
          durStr = fmtDur(run.duration_ms);
        } else if (run?.started_at && !run?.finished_at) {
          durStr = '…';
        }

        const isSelected = selectedTaskId === taskId;
        const exitCode = run?.exit_code;
        const hasExit = exitCode != null;
        const exitOk = exitCode === 0;
        const exitBad = hasExit && exitCode !== 0;
        const isSkipped = run?.status === 'skipped';

        // 运行中任务用蓝色，跳过用金黄色，已完成用绿/红，其余用类型颜色
        const badgeBg = isRunning ? 'rgba(59,130,246,0.12)' : isSkipped ? 'rgba(250,173,20,0.12)' : exitOk ? 'rgba(16,185,129,0.12)' : exitBad ? 'rgba(239,68,68,0.12)' : TYPE_COLOR[type] + '18';
        const badgeColor = isRunning ? '#3b82f6' : isSkipped ? '#faad14' : exitOk ? '#10b981' : exitBad ? '#ef4444' : TYPE_COLOR[type];

        // Task-level phase groups
        const taskSetup = taskPhaseMap.get(taskId)?.filter((g) => g.phase === 'setup') || [];
        const taskTeardown = taskPhaseMap.get(taskId)?.filter((g) => g.phase === 'teardown') || [];
        const taskPhaseChildren = [...taskSetup.map(buildPhaseNode), ...taskTeardown.map(buildPhaseNode)];

        // Issue #72: 右键重试 — 终态任务均可重试（含 skipped：策略失败导致未运行的任务也需要重试）
        const canRetry = !isLive && !!run;
        const retryCount = retryCounts?.[taskId] ?? 0;

        const menuItems: Array<{ key: string; label: React.ReactNode; icon?: React.ReactNode } | { type: 'divider' }> = [];
        if (canRetry) {
          menuItems.push({ key: 'retry', label: '重试此任务', icon: <RotateCcw size={14} /> });
        }
        if (retryCount > 0) {
          menuItems.push({ type: 'divider' as const });
          menuItems.push({ key: 'versions', label: `重试版本 (${retryCount})`, icon: <History size={14} /> });
        }

        const titleContent = (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', minWidth: 0, whiteSpace: 'nowrap' }}>
            <style>{BREATHING_STYLE}</style>
            <Tooltip title={isRunning ? '运行中' : isSkipped ? '已跳过' : hasExit ? `Exit ${exitCode} — ${exitOk ? '成功' : '失败'}` : type}>
              <span
                className={isRunning ? 'breathing-badge' : undefined}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 28,
                  height: 18,
                  fontSize: 10,
                  fontWeight: 600,
                  borderRadius: 4,
                  background: badgeBg,
                  color: badgeColor,
                  flexShrink: 0,
                  ...(isRunning ? { animation: 'breathing 2s ease-in-out infinite' } : {}),
                }}
              >
                {TYPE_LABEL[type]}
              </span>
            </Tooltip>
            <span style={{ fontSize: 13, fontWeight: isSelected ? 600 : isRunning ? 500 : 400, color: isSelected ? '#1d4ed8' : isRunning ? '#1d4ed8' : exitBad ? '#b91c1c' : '#374151', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>
              {task.name}
            </span>
            {retryCount > 0 && (
              <Tooltip title={`${retryCount} 个重试版本`}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 16, height: 16, fontSize: 10, fontWeight: 600, borderRadius: 8, padding: '0 4px', background: 'rgba(139,92,246,0.14)', color: '#8b5cf6', flexShrink: 0 }}>
                  {retryCount}
                </span>
              </Tooltip>
            )}
            {isRunning && (
              <Loader2 size={12} color="#3b82f6" className="animate-spin" style={{ flexShrink: 0 }} />
            )}
            {run?.error && (
              <Tooltip title={run.error} placement="topRight" styles={{ root: { maxWidth: 420 } }}>
                <ExclamationCircleOutlined style={{ color: '#ef4444', fontSize: 12, flexShrink: 0 }} />
              </Tooltip>
            )}
            <span style={{ flex: 1, minWidth: 4 }} />
            {durStr && (
              <Tooltip title={run?.started_at ? `开始: ${new Date(run.started_at).toLocaleString('zh-CN')}` : ''}>
                <span style={{ fontSize: 11, color: isRunning ? '#3b82f6' : '#9ca3af', flexShrink: 0 }}>{durStr}</span>
              </Tooltip>
            )}
          </div>
        );

        return {
          key: taskId,
          title: menuItems.length > 0 ? (
            <Dropdown
              trigger={['contextMenu']}
              menu={{
                items: menuItems,
                onClick: ({ key }) => {
                  if (key === 'retry') onRetry?.(taskId);
                  if (key === 'versions') onShowVersions?.(taskId);
                },
              }}
            >
              <div onContextMenu={(e) => e.preventDefault()}>{titleContent}</div>
            </Dropdown>
          ) : titleContent,
          ...(taskPhaseChildren.length > 0 ? { children: taskPhaseChildren } : {}),
        };
      });

      // Sub-level children: SETUP nodes + task nodes + TEARDOWN nodes
      const children: DataNode[] = [
        ...subSetup.map(buildPhaseNode),
        ...taskNodes,
        ...subTeardown.map(buildPhaseNode),
      ];

      return {
        key: subKey,
        title: (
          <div
            onClick={(e) => {
              e.stopPropagation();
              setExpandedKeys(prev =>
                prev.includes(subKey) ? prev.filter(k => k !== subKey) : [...prev, subKey]
              );
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', whiteSpace: 'nowrap', cursor: 'pointer', minWidth: 0 }}
          >
            <PartitionOutlined style={{ color: '#8b5cf6', flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>{sub.name}</span>
            <span style={{ flex: 1, minWidth: 4 }} />
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 20, height: 20, fontSize: 11, fontWeight: 600, borderRadius: 6, padding: '0 6px', background: '#8b5cf6' + '14', color: '#8b5cf6', flexShrink: 0 }}>
              {sub.tasks.length}
            </span>
          </div>
        ),
        children,
      };
    });

    // Pipeline-level SETUP/TEARDOWN as first/last root nodes
    const pipelineSetup = pipelinePhases.filter((g) => g.phase === 'setup').map(buildPhaseNode);
    const pipelineTeardown = pipelinePhases.filter((g) => g.phase === 'teardown').map(buildPhaseNode);

    return [...pipelineSetup, ...nodes, ...pipelineTeardown];
  }, [pipeline, runMap, selectedTaskId, phaseGroups, isLive, onRetry, onShowVersions, retryCounts]);

  const selectedKeys = selectedTaskId ? [selectedTaskId] : [];

  return (
    <div style={{ height: '100%', overflowY: 'auto', overflowX: 'hidden', background: '#fafafa', borderRight: '1px solid #e5e7eb' }}>
      <style>{`.task-tree .ant-tree-switcher{width:0!important;padding:0!important;min-width:0!important;overflow:hidden!important}`}</style>
      <div className="px-3 py-2 border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <AppstoreOutlined style={{ color: '#3b82f6', flexShrink: 0 }} />
          <span className="text-sm font-medium truncate">{pipeline.name}</span>
        </div>
      </div>
      <Tree
        className="task-tree"
        treeData={treeData}
        expandedKeys={expandedKeys}
        onExpand={(keys) => setExpandedKeys(keys)}
        selectedKeys={selectedKeys}
        onSelect={(keys) => {
          const key = keys[0] as string | undefined;
          if (key && key.startsWith('sub-')) return;
          onSelect(key ?? null);
        }}
        blockNode
        style={{ padding: '6px 0' }}
      />
    </div>
  );
}
