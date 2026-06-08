import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { PipelineDetail, TaskStatus } from '@/types';
import { applyDagreLayout } from '@/utils/dagreLayout';

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

    // 记录任务执行顺序编号（全局递增）
    const taskOrderMap = new Map<string, number>();
    let orderIndex = 1;

    subpipelines.forEach((sub) => {
      const ids: string[] = [];

      sub.tasks.forEach((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];

        taskOrderMap.set(taskId, orderIndex++);

        taskNodes.push({
          id: taskId,
          type: 'taskNode',
          position: { x: 0, y: 0 },
          data: {
            task,
            subpipelineName: sub.name,
            status,
            order: taskOrderMap.get(taskId),
          },
        });

        ids.push(taskId);

        // 任务间显式依赖边
        task.depends_on.forEach((dep) => {
          const sourceId = `${sub.name}.${dep}`;
          taskEdges.push({
            id: `${sourceId}-${taskId}`,
            source: sourceId,
            target: taskId,
            type: 'smoothstep',
            animated: true,
          });
        });
      });

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
          });
        }
      }
    });

    // 使用 dagre 布局任务节点
    const layoutedTaskNodes = applyDagreLayout(taskNodes, taskEdges);

    return {
      nodes: layoutedTaskNodes,
      edges: taskEdges,
    };
  }, [pipeline, taskStatuses]);
}
