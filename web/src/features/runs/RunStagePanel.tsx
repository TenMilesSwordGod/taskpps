import { useMemo } from 'react';
import { Tooltip } from 'antd';
import { Check, X, Loader2, SkipForward, Ban, Clock } from 'lucide-react';
import type { PipelineDetail, TaskRunResponse, TaskStatus } from '@/types';

const STATUS_META: Record<
  TaskStatus,
  { color: string; label: string; Icon: typeof Check }
> = {
  pending: { color: '#9ca3af', label: '等待中', Icon: Clock },
  running: { color: '#60a5fa', label: '运行中', Icon: Loader2 },
  success: { color: '#34d399', label: '成功', Icon: Check },
  failed: { color: '#f87171', label: '失败', Icon: X },
  skipped: { color: '#fbbf24', label: '已跳过', Icon: SkipForward },
  cancelled: { color: '#fb923c', label: '已取消', Icon: Ban },
};

const NODE_SIZE = 18;
const ICON_SIZE = 10;

type Strategy = 'parallel' | 'sequential';

interface StageNode {
  taskId: string;
  name: string;
  subpipeline: string;
  status: TaskStatus;
  strategy: Strategy;
}

interface StageGroup {
  subpipeline: string;
  strategy: Strategy;
  nodes: StageNode[];
}

interface RunStagePanelProps {
  pipeline?: PipelineDetail;
  taskRuns?: TaskRunResponse[];
}

/** 任务节点：带状态图标的圆点 */
function StageTaskNode({ node }: { node: StageNode }) {
  const { color, label, Icon } = STATUS_META[node.status];
  const isRunning = node.status === 'running';

  return (
    <Tooltip title={`${node.subpipeline ? `${node.subpipeline} / ` : ''}${node.name} · ${label}`}>
      <span
        data-testid="stage-node"
        data-task-name={node.taskId}
        data-status={node.status}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: NODE_SIZE,
          height: NODE_SIZE,
          borderRadius: '50%',
          background: color,
          color: '#fff',
          flexShrink: 0,
          cursor: 'default',
        }}
      >
        <Icon size={ICON_SIZE} className={isRunning ? 'animate-spin' : undefined} />
      </span>
    </Tooltip>
  );
}

/** stage 之间的带箭头连线 */
function ArrowLine() {
  return (
    <svg width="20" height="10" style={{ flexShrink: 0, margin: '0 2px' }}>
      <defs>
        <marker
          id="stage-arrow"
          markerWidth="6"
          markerHeight="6"
          refX="5"
          refY="3"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <polygon points="0 0, 6 3, 0 6" fill="#d1d5db" />
        </marker>
      </defs>
      <line
        x1="0"
        y1="5"
        x2="16"
        y2="5"
        stroke="#d1d5db"
        strokeWidth={1}
        markerEnd="url(#stage-arrow)"
      />
    </svg>
  );
}

/** 任务之间水平细线 */
function HLine() {
  return (
    <div
      style={{
        width: 10,
        height: 1,
        background: '#e5e7eb',
        margin: '0 2px',
        flexShrink: 0,
      }}
    />
  );
}

/** 并行任务之间垂直细线 */
function VLine() {
  return (
    <div
      style={{
        width: 1,
        height: 6,
        background: '#e5e7eb',
        flexShrink: 0,
      }}
    />
  );
}

/** 运行历史详情页顶部的小面板：Jenkins Blue Ocean 风格的 stage 级执行图 */
export default function RunStagePanel({ pipeline, taskRuns }: RunStagePanelProps) {
  const groups = useMemo<StageGroup[]>(() => {
    const runMap = new Map<string, TaskRunResponse>();
    for (const t of taskRuns ?? []) {
      runMap.set(t.task_name, t);
    }

    const list: StageGroup[] = [];
    const seen = new Set<string>();

    const makeNode = (
      subpipeline: string,
      name: string,
      strategy: Strategy,
    ): StageNode => {
      const taskId = subpipeline ? `${subpipeline}.${name}` : name;
      seen.add(taskId);
      return {
        taskId,
        name,
        subpipeline,
        status: runMap.get(taskId)?.status ?? 'pending',
        strategy,
      };
    };

    if (pipeline?.pipelines) {
      for (const sub of pipeline.pipelines) {
        const strategy: Strategy = sub.config?.execution_strategy === 'parallel' ? 'parallel' : 'sequential';
        const nodes = sub.tasks.map((task) => makeNode(sub.name, task.name, strategy));
        if (nodes.length > 0) {
          list.push({ subpipeline: sub.name, strategy, nodes });
        }
      }
    }

    if (pipeline?.tasks) {
      const nodes = pipeline.tasks.map((task) => makeNode('', task.name, 'sequential'));
      if (nodes.length > 0) {
        list.push({ subpipeline: '默认', strategy: 'sequential', nodes });
      }
    }

    // 兜底：运行记录里有但快照定义里没有的任务
    for (const t of taskRuns ?? []) {
      if (!seen.has(t.task_name)) {
        const dotIdx = t.task_name.indexOf('.');
        const subName = dotIdx > 0 ? t.task_name.slice(0, dotIdx) : '其他';
        const taskName = dotIdx > 0 ? t.task_name.slice(dotIdx + 1) : t.task_name;
        const node: StageNode = {
          taskId: t.task_name,
          name: taskName,
          subpipeline: subName,
          status: t.status,
          strategy: 'sequential',
        };
        const group = list.find((g) => g.subpipeline === subName);
        if (group) {
          group.nodes.push(node);
        } else {
          list.push({ subpipeline: subName, strategy: 'sequential', nodes: [node] });
        }
      }
    }

    return list;
  }, [pipeline, taskRuns]);

  if (groups.length === 0) return null;

  const children: React.ReactNode[] = [];
  groups.forEach((group, index) => {
    const isParallel = group.strategy === 'parallel';
    children.push(
      <div
        key={group.subpipeline}
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 4,
          flexShrink: 0,
        }}
      >
        <div
          data-testid={`stage-tasks-${group.subpipeline}`}
          data-stage-name={group.subpipeline}
          style={{
            display: 'flex',
            flexDirection: isParallel ? 'column' : 'row',
            alignItems: 'center',
            gap: isParallel ? 2 : 0,
          }}
        >
          {group.nodes.map((node, nodeIndex) => {
            const isLast = nodeIndex === group.nodes.length - 1;
            return (
              <div
                key={node.taskId}
                style={{
                  display: 'flex',
                  flexDirection: isParallel ? 'column' : 'row',
                  alignItems: 'center',
                }}
              >
                <StageTaskNode node={node} />
                {!isLast && (isParallel ? <VLine /> : <HLine />)}
              </div>
            );
          })}
        </div>
        <span
          style={{
            fontSize: 11,
            color: '#6b7280',
            maxWidth: 80,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {group.subpipeline}
        </span>
      </div>,
    );

    if (index < groups.length - 1) {
      children.push(<ArrowLine key={`arrow-${group.subpipeline}`} />);
    }
  });

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        minWidth: 0,
        maxWidth: 520,
        padding: '2px 4px',
        overflowX: 'auto',
        scrollbarWidth: 'none',
        msOverflowStyle: 'none',
      }}
    >
      {children}
    </div>
  );
}
