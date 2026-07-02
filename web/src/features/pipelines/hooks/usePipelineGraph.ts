import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { PipelineDetail, TaskStatus, PostConfig } from '@/types';
import type { PostVariant } from '../nodes/PostTaskNode';
import { applyDagreLayout } from '@/utils/dagreLayout';

const GROUP_PADDING_X = 24;
const GROUP_PADDING_Y = 48;
const GROUP_HEADER = 28;
const TASK_W = 200;
const TASK_H = 48;
const POST_H = 30;

interface UsePipelineGraphOptions {
  pipeline: PipelineDetail | undefined;
  taskStatuses?: Record<string, TaskStatus>;
}

/** 统计一个 post config 中的 post 子节点数量 */
function countPostTasks(post: PostConfig | null | undefined): number {
  if (!post) return 0;
  let count = 0;
  if (post.on_fail) count += post.on_fail.length;
  if (post.on_success) count += post.on_success.length;
  if (post.always) count += post.always.length;
  return count;
}

export function usePipelineGraph({ pipeline, taskStatuses }: UsePipelineGraphOptions) {
  return useMemo(() => {
    if (!pipeline) return { nodes: [] as Node[], edges: [] as Edge[] };

    const subpipelines = pipeline.pipelines || [];
    const taskNodes: Node[] = [];
    const taskEdges: Edge[] = [];
    const groupNodes: Node[] = [];

    let orderIndex = 1;
    const subpipelineTaskIds: string[][] = [];

    subpipelines.forEach((sub) => {
      const ids: string[] = [];
      const groupId = `__group__${sub.name}`;

      sub.tasks?.forEach((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];

        taskNodes.push({
          id: taskId,
          type: 'taskNode',
          parentId: groupId,
          extent: 'parent' as const,
          position: { x: 0, y: 0 },
          data: { task, subpipelineName: sub.name, status, order: orderIndex },
        });

        orderIndex++;
        ids.push(taskId);

        task.depends_on?.forEach((dep) => {
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

      const strategy = sub.config?.execution_strategy
        ?? pipeline.options?.execution_strategy
        ?? pipeline.config?.execution_strategy
        ?? 'sequential';

      if (strategy !== 'parallel') {
        for (let i = 1; i < ids.length; i++) {
          const currTask = sub.tasks?.[i];
          if (currTask && (currTask.depends_on?.length ?? 0) === 0) {
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
      }

      // 预计算该 group 的 post 子节点数量
      let postCount = countPostTasks(sub.post);
      for (const task of sub.tasks ?? []) {
        postCount += countPostTasks(task.post);
      }

      const hasChildren = ids.length > 0;
      const taskAreaH = ids.length * (TASK_H + 30) - 30;
      const postAreaH = postCount > 0 ? postCount * POST_H + 8 : 0;
      groupNodes.push({
        id: groupId,
        type: 'subpipelineGroup',
        position: { x: 0, y: 0 },
        style: {
          width: hasChildren ? TASK_W + GROUP_PADDING_X * 2 : 200,
          height: hasChildren
            ? taskAreaH + postAreaH + GROUP_PADDING_Y * 2 + GROUP_HEADER
            : 100,
        },
        data: { label: sub.name, taskCount: ids.length },
      });
    });

    // 跨 subpipeline 边
    subpipelines.forEach((sub, idx) => {
      sub.depends_on?.forEach((depSubName) => {
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

    // === Post 阶段节点 ===
    const postNodes: Node[] = [];
    let postIndex = 0;

    function addPostNodes(post: PostConfig | null | undefined, parentTaskId: string, parentGroupId: string) {
      if (!post) return;
      const variants: PostVariant[] = ['on_fail', 'on_success', 'always'];
      for (const variant of variants) {
        const tasks = post[variant];
        if (!tasks || tasks.length === 0) continue;
        for (const pt of tasks) {
          const postId = `__post__${postIndex++}_${parentTaskId}_${variant}`;
          postNodes.push({
            id: postId,
            type: 'postTask',
            parentId: parentGroupId,
            extent: 'parent' as const,
            position: { x: 0, y: 0 },
            data: { label: pt.name, variant, parentTaskId },
          });
          taskEdges.push({
            id: `post-edge-${parentTaskId}-${postId}`,
            source: parentTaskId,
            target: postId,
            type: 'smoothstep',
            animated: false,
            markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
            style: { stroke: '#9ca3af', strokeWidth: 1.5, strokeDasharray: '5 3' },
          });
        }
      }
    }

    subpipelines.forEach((sub, idx) => {
      const groupId = `__group__${sub.name}`;
      addPostNodes(sub.post, subpipelineTaskIds[idx]?.[subpipelineTaskIds[idx].length - 1] ?? '', groupId);
      sub.tasks?.forEach((task) => {
        addPostNodes(task.post, `${sub.name}.${task.name}`, groupId);
      });
    });

    // === Start / End 哨兵节点 ===
    const startNode: Node = {
      id: '__start__',
      type: 'startEnd',
      position: { x: 0, y: 0 },
      data: { variant: 'start' },
    };
    const endNode: Node = {
      id: '__end__',
      type: 'startEnd',
      position: { x: 0, y: 0 },
      data: { variant: 'end' },
    };

    // Start/End 连接到 group 节点（不是 task 节点），减少边路由复杂度
    const hasIncoming = new Set<string>();
    const hasOutgoing = new Set<string>();
    for (const e of taskEdges) {
      hasIncoming.add(e.target);
      hasOutgoing.add(e.source);
    }

    const allGroupIds = groupNodes.map((n) => n.id);
    const rootGroupIds = allGroupIds.filter((id) => !hasIncoming.has(id));
    const leafGroupIds = allGroupIds.filter((id) => !hasOutgoing.has(id));

    // 如果 group 没有入边（根 group），Start → 该 group
    for (const gid of rootGroupIds) {
      taskEdges.push({
        id: `start-to-${gid}`,
        source: '__start__',
        target: gid,
        type: 'smoothstep',
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        style: { stroke: '#22c55e', strokeWidth: 1.5 },
      });
    }
    // 如果 group 没有出边（叶子 group），该 group → End
    for (const gid of leafGroupIds) {
      taskEdges.push({
        id: `${gid}-to-end`,
        source: gid,
        target: '__end__',
        type: 'smoothstep',
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        style: { stroke: '#9ca3af', strokeWidth: 1.5 },
      });
    }
    // 无 group 时（只有 tasks），直接连 task
    if (allGroupIds.length === 0) {
      const allTaskIds = taskNodes.map((n) => n.id);
      for (const tid of allTaskIds.filter((id) => !hasIncoming.has(id))) {
        taskEdges.push({
          id: `start-to-${tid}`,
          source: '__start__',
          target: tid,
          type: 'smoothstep',
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
          style: { stroke: '#22c55e', strokeWidth: 1.5 },
        });
      }
      for (const tid of allTaskIds.filter((id) => !hasOutgoing.has(id))) {
        taskEdges.push({
          id: `${tid}-to-end`,
          source: tid,
          target: '__end__',
          type: 'smoothstep',
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
          style: { stroke: '#9ca3af', strokeWidth: 1.5 },
        });
      }
    }

    // dagre 布局
    const groupSizes = new Map<string, { width: number; height: number }>();
    for (const gn of groupNodes) {
      const w = (gn.style as { width?: number })?.width ?? 200;
      const h = (gn.style as { height?: number })?.height ?? 100;
      groupSizes.set(gn.id, { width: w, height: h });
    }

    const allNodes = [...groupNodes, ...taskNodes, ...postNodes, startNode, endNode];
    const layoutedNodes = applyDagreLayout(allNodes, taskEdges, groupSizes);

    // dagre 布局后，固定 Start 在最顶部（End 在 group resize 后再定位）
    let minY = Infinity;
    for (const n of layoutedNodes) {
      if (n.id === '__start__' || n.id === '__end__') continue;
      minY = Math.min(minY, n.position.y);
    }
    if (!isFinite(minY)) minY = 0;
    for (const n of layoutedNodes) {
      if (n.id === '__start__') {
        n.position.y = minY - 50;
      }
    }

    // 子节点位置转为相对于 group 的 offset
    const layoutedMap = new Map(layoutedNodes.map((n) => [n.id, n]));

    const finalNodes: Node[] = [];
    for (const node of layoutedNodes) {
      const n = { ...node };
      if (node.parentId) {
        const parent = layoutedMap.get(node.parentId);
        if (parent) {
          n.position = {
            x: n.position.x - parent.position.x,
            y: n.position.y - parent.position.y,
          };
        }
      }
      finalNodes.push(n);
    }

    // 调整 group 尺寸以包裹所有子节点（含 post 节点）
    for (const node of finalNodes) {
      if (node.type === 'subpipelineGroup') {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const child of finalNodes) {
          if (child.parentId === node.id) {
            const cw = child.type === 'postTask' ? 160 : TASK_W;
            const ch = child.type === 'postTask' ? POST_H : TASK_H;
            minX = Math.min(minX, child.position.x);
            minY = Math.min(minY, child.position.y);
            maxX = Math.max(maxX, child.position.x + cw);
            maxY = Math.max(maxY, child.position.y + ch);
          }
        }
        if (minX < Infinity) {
          node.style = {
            ...((node.style as object) || {}),
            width: maxX - minX + GROUP_PADDING_X * 2,
            height: maxY - minY + GROUP_PADDING_Y * 2 + GROUP_HEADER,
          };
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

    // group resize 后，用实际 group box 高度定位 End 到最底部
    let finalMaxY = -Infinity;
    for (const node of finalNodes) {
      if (node.id === '__start__' || node.id === '__end__') continue;
      const nodeBottom = node.position.y + ((node.type === 'subpipelineGroup')
        ? ((node.style as { height?: number })?.height ?? 100)
        : TASK_H);
      finalMaxY = Math.max(finalMaxY, nodeBottom);
    }
    if (!isFinite(finalMaxY)) finalMaxY = 100;
    for (const node of finalNodes) {
      if (node.id === '__end__') {
        node.position.y = finalMaxY + 40;
      }
    }

    return { nodes: finalNodes, edges: taskEdges };
  }, [pipeline, taskStatuses]);
}
