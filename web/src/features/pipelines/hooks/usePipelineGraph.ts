import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { PipelineDetail, TaskStatus } from '@/types';
import { applyDagreLayout } from '@/utils/dagreLayout';

const GROUP_PADDING_X = 24;
const GROUP_PADDING_Y = 48;
const GROUP_HEADER = 28;
const TASK_W = 200;
const TASK_H = 48;

interface UsePipelineGraphOptions {
  /** 流水线详情数据 */
  pipeline: PipelineDetail | undefined;
  /** 任务状态映射（运行视图下使用），key 为 "subpipeline.task" 格式 */
  taskStatuses?: Record<string, TaskStatus>;
}

export function usePipelineGraph({ pipeline, taskStatuses }: UsePipelineGraphOptions) {
  return useMemo(() => {
    if (!pipeline) return { nodes: [] as Node[], edges: [] as Edge[] };

    const subpipelines = pipeline.pipelines || [];
    const taskNodes: Node[] = [];
    const taskEdges: Edge[] = [];
    const groupNodes: Node[] = [];

    // 记录任务执行顺序编号（全局递增）
    let orderIndex = 1;

    // 收集每个 subpipeline 的 task IDs（用于跨 subpipeline 边）
    const subpipelineTaskIds: string[][] = [];

    subpipelines.forEach((sub) => {
      const ids: string[] = [];
      const groupId = `__group__${sub.name}`;

      sub.tasks.forEach((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];

        taskNodes.push({
          id: taskId,
          type: 'taskNode',
          parentId: groupId,
          extent: 'parent' as const,
          position: { x: 0, y: 0 },
          data: {
            task,
            subpipelineName: sub.name,
            status,
            order: orderIndex,
          },
        });

        orderIndex++;
        ids.push(taskId);

        // 任务间显式依赖边
        task.depends_on.forEach((dep) => {
          const sourceId = `${sub.name}.${dep}`;
          taskEdges.push({
            id: `dep-${sourceId}-${taskId}`,
            source: sourceId,
            target: taskId,
            type: 'smoothstep',
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
          });
        });
      });

      subpipelineTaskIds.push(ids);

      // 对于没有显式依赖的任务，按 YAML 顺序添加隐式顺序边
      for (let i = 1; i < ids.length; i++) {
        const currTask = sub.tasks[i];
        if (currTask.depends_on.length === 0) {
          taskEdges.push({
            id: `implicit-${ids[i - 1]}-${ids[i]}`,
            source: ids[i - 1],
            target: ids[i],
            type: 'smoothstep',
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
          });
        }
      }

      // 创建子流水线分组节点
      const hasChildren = ids.length > 0;
      groupNodes.push({
        id: groupId,
        type: 'subpipelineGroup',
        position: { x: 0, y: 0 },
        style: {
          width: hasChildren ? TASK_W + GROUP_PADDING_X * 2 : 200,
          height: hasChildren
            ? ids.length * (TASK_H + 30) + GROUP_PADDING_Y * 2 - 30 + GROUP_HEADER
            : 100,
        },
        data: {
          label: sub.name,
          taskCount: ids.length,
        },
      });
    });

    // 跨 subpipeline 边：基于 SubPipeline.depends_on
    subpipelines.forEach((sub, idx) => {
      sub.depends_on.forEach((depSubName) => {
        const sourceIdx = subpipelines.findIndex((s) => s.name === depSubName);
        if (sourceIdx >= 0 && sourceIdx < subpipelineTaskIds.length) {
          const sourceIds = subpipelineTaskIds[sourceIdx];
          const targetIds = subpipelineTaskIds[idx];
          if (sourceIds.length > 0 && targetIds.length > 0) {
            taskEdges.push({
              id: `cross-sub-${depSubName}-${sub.name}`,
              source: sourceIds[sourceIds.length - 1],
              target: targetIds[0],
              type: 'smoothstep',
              animated: true,
              markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: '#f59e0b' },
              style: { stroke: '#f59e0b', strokeWidth: 2, strokeDasharray: '6 3' },
            });
          }
        }
      });
    });

    // 使用 dagre 布局所有节点（含分组节点）
    const allNodes = [...groupNodes, ...taskNodes];
    const layoutedNodes = applyDagreLayout(allNodes, taskEdges);

    // dagre 调整位置后，为每个分组节点计算其子节点的边界，
    // 然后更新子节点 position 为相对于分组的 offset
    const layoutedMap = new Map(layoutedNodes.map((n) => [n.id, n]));

    const finalNodes: Node[] = [];
    for (const node of layoutedNodes) {
      const n = { ...node };
      if (node.parentId) {
        const parent = layoutedMap.get(node.parentId);
        if (parent) {
          // 子节点位置相对于分组节点
          n.position = {
            x: n.position.x - parent.position.x,
            y: n.position.y - parent.position.y,
          };
        }
      }
      finalNodes.push(n);
    }

    // 调整分组节点尺寸以包裹所有子节点
    for (const node of finalNodes) {
      if (node.type === 'subpipelineGroup') {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const child of finalNodes) {
          if (child.parentId === node.id) {
            minX = Math.min(minX, child.position.x);
            minY = Math.min(minY, child.position.y);
            maxX = Math.max(maxX, child.position.x + TASK_W);
            maxY = Math.max(maxY, child.position.y + TASK_H);
          }
        }
        if (minX < Infinity) {
          node.style = {
            ...((node.style as object) || {}),
            width: maxX - minX + GROUP_PADDING_X * 2,
            height: maxY - minY + GROUP_PADDING_Y * 2 + GROUP_HEADER,
          };
          // 偏移子节点使其在分组内居中且有 padding
          for (const child of finalNodes) {
            if (child.parentId === node.id) {
              child.position = {
                x: child.position.x - minX + GROUP_PADDING_X,
                y: child.position.y - minY + GROUP_PADDING_Y + GROUP_HEADER,
              };
            }
          }
        }
      }
    }

    return {
      nodes: finalNodes,
      edges: taskEdges,
    };
  }, [pipeline, taskStatuses]);
}
