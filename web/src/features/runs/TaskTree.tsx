import { useMemo, useState, useEffect } from 'react';
import { Tree, Tooltip } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { PartitionOutlined, AppstoreOutlined, ExclamationCircleOutlined } from '@ant-design/icons';

import { useRunConsole } from '@/api/runs';
import type { PipelineDetail, TaskStatus, SubPipeline, TaskYAML } from '@/types';

interface TaskRunInfo {
  task_name: string;
  status: TaskStatus;
  exit_code: number | null;
  error?: string | null;
  started_at: string | null;
  finished_at: string | null;
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
export default function TaskTree({ pipeline, taskRuns, selectedTaskId, onSelect, debugVisible, runId }: TaskTreeProps) {
  const runMap = useMemo(() => {
    if (!taskRuns) return new Map<string, TaskRunInfo>();
    const m = new Map<string, TaskRunInfo>();
    for (const r of taskRuns) m.set(r.task_name, r);
    return m;
  }, [taskRuns]);

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

        let durStr: string | null = null;
        if (run?.started_at && run?.finished_at) {
          const dur = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
          durStr = fmtDur(Math.max(0, dur));
        } else if (run?.started_at && !run?.finished_at) {
          durStr = '…';
        }

        const isSelected = selectedTaskId === taskId;
        const exitCode = run?.exit_code;
        const hasExit = exitCode != null;
        const exitOk = exitCode === 0;
        const exitBad = hasExit && exitCode !== 0;

        const badgeBg = exitOk ? 'rgba(16,185,129,0.12)' : exitBad ? 'rgba(239,68,68,0.12)' : TYPE_COLOR[type] + '18';
        const badgeColor = exitOk ? '#10b981' : exitBad ? '#ef4444' : TYPE_COLOR[type];

        // Task-level phase groups
        const taskSetup = taskPhaseMap.get(taskId)?.filter((g) => g.phase === 'setup') || [];
        const taskTeardown = taskPhaseMap.get(taskId)?.filter((g) => g.phase === 'teardown') || [];
        const taskPhaseChildren = [...taskSetup.map(buildPhaseNode), ...taskTeardown.map(buildPhaseNode)];

        return {
          key: taskId,
          title: (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0', minWidth: 0, whiteSpace: 'nowrap' }}>
              <Tooltip title={hasExit ? `Exit ${exitCode} — ${exitOk ? '成功' : '失败'}` : type}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 18, fontSize: 10, fontWeight: 600, borderRadius: 4, background: badgeBg, color: badgeColor, flexShrink: 0 }}>
                  {TYPE_LABEL[type]}
                </span>
              </Tooltip>
              <span style={{ fontSize: 13, fontWeight: isSelected ? 600 : 400, color: isSelected ? '#1d4ed8' : exitBad ? '#b91c1c' : '#374151', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>
                {task.name}
              </span>
              {run?.error && (
                <Tooltip title={run.error} placement="topRight" overlayStyle={{ maxWidth: 420 }}>
                  <ExclamationCircleOutlined style={{ color: '#ef4444', fontSize: 12, flexShrink: 0 }} />
                </Tooltip>
              )}
              <span style={{ flex: 1, minWidth: 4 }} />
              {durStr && (
                <Tooltip title={run?.started_at ? `开始: ${new Date(run.started_at).toLocaleString('zh-CN')}` : ''}>
                  <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0 }}>{durStr}</span>
                </Tooltip>
              )}
            </div>
          ),
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
  }, [pipeline, runMap, selectedTaskId, phaseGroups]);

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
