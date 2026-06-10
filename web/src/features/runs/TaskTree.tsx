import { useMemo } from 'react';
import { Tree, Tooltip } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { PartitionOutlined, AppstoreOutlined } from '@ant-design/icons';
import { AlertCircle, CheckCircle2, Clock } from 'lucide-react';
import StatusTag from '@/components/StatusTag';
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

/** 格式化毫秒 */
function fmtDur(ms: number): string {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  if (m > 0) return `${m}m${s % 60}s`;
  return `${s}s`;
}

/** 紧凑层级任务树 */
export default function TaskTree({ pipeline, taskStatuses, taskRuns, selectedTaskId, onSelect }: TaskTreeProps) {
  const runMap = useMemo(() => {
    if (!taskRuns) return new Map<string, TaskRunInfo>();
    const m = new Map<string, TaskRunInfo>();
    for (const r of taskRuns) m.set(r.task_name, r);
    return m;
  }, [taskRuns]);

  const treeData = useMemo<DataNode[]>(() => {
    const subpipelines: SubPipeline[] = pipeline.pipelines || [];
    return subpipelines.map((sub) => {
      const children: DataNode[] = sub.tasks.map((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];
        const run = runMap.get(taskId);
        const type = inferTaskType(task);

        // 计算执行时间
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
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '2px 0',
                minWidth: 0,
                whiteSpace: 'nowrap',
              }}
            >
              {/* 类型标签 */}
              <Tooltip title={type}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 28,
                    height: 18,
                    fontSize: 10,
                    fontWeight: 600,
                    borderRadius: 4,
                    background: TYPE_COLOR[type] + '18',
                    color: TYPE_COLOR[type],
                    flexShrink: 0,
                  }}
                >
                  {TYPE_LABEL[type]}
                </span>
              </Tooltip>

              {/* 任务名 */}
              <span
                style={{
                  fontSize: 13,
                  fontWeight: isSelected ? 600 : 400,
                  color: isSelected ? '#1d4ed8' : '#374151',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  minWidth: 0,
                }}
              >
                {task.name}
              </span>

              {/* 右侧信息 */}
              <span style={{ flex: 1 }} />

              {/* 执行时间 */}
              {durStr && (
                <Tooltip title={run?.started_at ? `开始: ${new Date(run.started_at).toLocaleString('zh-CN')}` : ''}>
                  <span
                    style={{
                      fontSize: 11,
                      color: '#9ca3af',
                      flexShrink: 0,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 2,
                    }}
                  >
                    <Clock size={10} />
                    {durStr}
                  </span>
                </Tooltip>
              )}

              {/* Exit code */}
              {exitOk && (
                <Tooltip title="Exit 0 — 成功">
                  <span
                    style={{
                      fontSize: 11,
                      color: '#10b981',
                      fontWeight: 500,
                      flexShrink: 0,
                    }}
                  >
                    <CheckCircle2 size={10} style={{ verticalAlign: -1, marginRight: 2 }} />
                    0
                  </span>
                </Tooltip>
              )}
              {exitBad && (
                <Tooltip title={`Exit ${run!.exit_code} — 失败`}>
                  <span
                    style={{
                      fontSize: 11,
                      color: '#ef4444',
                      fontWeight: 500,
                      flexShrink: 0,
                    }}
                  >
                    <AlertCircle size={10} style={{ verticalAlign: -1, marginRight: 2 }} />
                    {run!.exit_code}
                  </span>
                </Tooltip>
              )}

              {/* 状态 */}
              {status && <StatusTag status={status} />}
            </div>
          ),
        };
      });

      return {
        key: `sub-${sub.name}`,
        title: (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '2px 0',
              whiteSpace: 'nowrap',
            }}
          >
            <PartitionOutlined style={{ color: '#8b5cf6', flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 600, color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>
              {sub.name}
            </span>
            <span style={{ flex: 1, minWidth: 4 }} />
            {/* 任务计数彩色徽标 */}
            <Tooltip title={`${sub.tasks.length} 个任务`}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  minWidth: 20,
                  height: 20,
                  fontSize: 11,
                  fontWeight: 600,
                  borderRadius: 6,
                  padding: '0 6px',
                  background: '#8b5cf6' + '14',
                  color: '#8b5cf6',
                  flexShrink: 0,
                }}
              >
                {sub.tasks.length}
              </span>
            </Tooltip>
          </div>
        ),
        children,
      };
    });
  }, [pipeline, taskStatuses, runMap, selectedTaskId]);

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
          if (key && key.startsWith('sub-')) return;
          onSelect(key ?? null);
        }}
        blockNode
        style={{ padding: '6px 0' }}
      />
    </div>
  );
}
