import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { PipelineDetail, TaskStatus, PostConfig } from '@/types';
import type { PostVariant } from '../nodes/PostTaskNode';
import { applyDagreLayout } from '@/utils/dagreLayout';

const GROUP_PADDING_X = 20;
const GROUP_PADDING_Y = 14;
const GROUP_GAP_Y = 24;
const GROUP_HEADER = 0;
// 顶部入口区域：top-out handle → 首 task/decision 的边需要垂直空间
const GROUP_ENTRY_AREA = 30;
// 底部出口区域：no/alt/lastTask 边汇聚到 exit handle 需要垂直空间
const GROUP_EXIT_AREA = 50;
const TASK_W = 150;
const TASK_H = 36;
const POST_H = 26;
const POST_W = 168;
const DECISION_SIZE = 76;

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

/** 默认流轨样式 */
const RAIL_STYLE = { stroke: '#94A3B8', strokeWidth: 1.5 };
const RAIL_MARKER = { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#94A3B8' };

/** Yes 路径边样式（绿色实线） */
const YES_STYLE = { stroke: '#16A34A', strokeWidth: 1.5 };
const YES_MARKER = { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#16A34A' };

/** alt 路径边样式（灰色虚线，表示带 when 的孤立 task 执行后经 group 输出点退出） */
const ALT_STYLE = { stroke: '#94A3B8', strokeWidth: 1, strokeDasharray: '3 3' };
const ALT_MARKER = { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#94A3B8' };
const ALT_LABEL_FILL = '#64748B';

function pushPlainEdge(
  taskEdges: Edge[],
  sourceId: string,
  targetId: string,
  edgeBaseId: string,
  markerEnd: Edge['markerEnd'],
  style?: Edge['style'],
) {
  taskEdges.push({
    id: edgeBaseId,
    source: sourceId,
    target: targetId,
    type: 'smoothstep',
    animated: false,
    markerEnd: markerEnd ?? RAIL_MARKER,
    style: style ?? RAIL_STYLE,
  });
}

export function usePipelineGraph({ pipeline, taskStatuses }: UsePipelineGraphOptions) {
  return useMemo(() => {
    if (!pipeline) return { nodes: [] as Node[], edges: [] as Edge[] };

    const subpipelines = pipeline.pipelines || [];
    const taskNodes: Node[] = [];
    const taskEdges: Edge[] = [];
    const groupNodes: Node[] = [];
    const decisionNodes: Node[] = [];
    let orderIndex = 1;
    const subpipelineTaskIds: string[][] = [];

    // 先收集所有任务节点和它们的 when 条件
    const taskWhenMap = new Map<string, string>(); // taskId → when expr
    const decisionTargetMap = new Map<string, string>(); // decisionId → 被跳过的 taskId
    // 收集所有显式 depends_on 关系（sourceId → targetId[]）
    const dependsOnMap = new Map<string, string[]>();
    // 收集所有隐式顺序关系
    const implicitEdges: [string, string][] = [];

    subpipelines.forEach((sub) => {
      const ids: string[] = [];
      const groupId = `__group__${sub.name}`;

      sub.tasks?.forEach((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];
        const whenExpr = task.when?.trim();

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

        if (whenExpr) {
          taskWhenMap.set(taskId, whenExpr);
        }

        // 收集显式 depends_on
        task.depends_on?.forEach((dep) => {
          const sourceId = `${sub.name}.${dep}`;
          if (!dependsOnMap.has(sourceId)) dependsOnMap.set(sourceId, []);
          dependsOnMap.get(sourceId)!.push(taskId);
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
          const prevId = ids[i - 1];
          const currId = ids[i];
          if (currTask && (currTask.depends_on?.length ?? 0) === 0) {
            implicitEdges.push([prevId, currId]);
          }
        }
      }

      // 预计算该 group 的 post 子节点数量
      let postCount = countPostTasks(sub.post);
      for (const task of sub.tasks ?? []) {
        postCount += countPostTasks(task.post);
      }

      const hasChildren = ids.length > 0;
      // decision 节点(76px)比 task(36px)高，行高取最大值避免低估高度
      const rowH = Math.max(TASK_H + 20, DECISION_SIZE + 20);
      const taskAreaH = ids.length * rowH - 20;
      const postAreaH = postCount > 0 ? postCount * (POST_H + 6) + 6 : 0;
      groupNodes.push({
        id: groupId,
        type: 'subpipelineGroup',
        position: { x: 0, y: 0 },
        style: {
          width: hasChildren ? Math.max(TASK_W, POST_W) + GROUP_PADDING_X * 2 : 200,
          height: hasChildren
            ? taskAreaH + postAreaH + GROUP_PADDING_Y * 2 + GROUP_HEADER + GROUP_ENTRY_AREA + GROUP_EXIT_AREA
            : 100,
        },
        data: { label: sub.name, taskCount: ids.length },
      });
    });

    // 收集所有任务 ID → 所属 group 映射
    const taskGroupMap = new Map<string, string>();
    for (const tn of taskNodes) {
      if (tn.parentId) taskGroupMap.set(tn.id, tn.parentId);
    }

    // === 构建边 ===
    // 对于有 when 条件的目标任务：
    //   source → decisionNode → (yes) → 条件任务
    //   no 路径由菱形 yes/no 标注隐含表达（不画 no 边到下游，避免与条件任务的出边交叉）
    // 对于无 when 条件的目标任务：source → target 直连

    // 处理显式 depends_on 边
    for (const [sourceId, targets] of dependsOnMap) {
      for (const targetId of targets) {
        const whenExpr = taskWhenMap.get(targetId);
        if (whenExpr) {
          const decisionId = `decision-${sourceId}-${targetId}`;
          const sourceGroup = taskGroupMap.get(sourceId);

          if (!decisionNodes.find((d) => d.id === decisionId)) {
            decisionNodes.push({
              id: decisionId,
              type: 'decisionNode',
              parentId: sourceGroup ?? undefined,
              extent: sourceGroup ? 'parent' as const : undefined,
              position: { x: 0, y: 0 },
              data: { when: whenExpr },
            });
          decisionTargetMap.set(decisionId, targetId);

            // source → decision
            pushPlainEdge(taskEdges, sourceId, decisionId, `dep-${sourceId}-${decisionId}`, RAIL_MARKER, RAIL_STYLE);

            // decision → (yes) → 条件任务
            taskEdges.push({
              id: `yes-${decisionId}-${targetId}`,
              source: decisionId,
              sourceHandle: 'yes',
              target: targetId,
              type: 'smoothstep',
              animated: false,
              label: 'yes',
              labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#16A34A' },
              labelBgStyle: { fill: '#F0FDF4', fillOpacity: 1 },
              labelBgPadding: [2, 4] as [number, number],
              labelBgBorderRadius: 3,
              markerEnd: YES_MARKER,
              style: YES_STYLE,
            });

            // no 路径由菱形标注隐含（不画边，避免交叉）
          }
        } else {
          pushPlainEdge(taskEdges, sourceId, targetId, `dep-${sourceId}-${targetId}`, RAIL_MARKER, RAIL_STYLE);
        }
      }
    }

    // 处理隐式顺序边
    for (const [prevId, currId] of implicitEdges) {
      const whenExpr = taskWhenMap.get(currId);
      if (whenExpr) {
        const decisionId = `decision-${prevId}-${currId}`;
        const sourceGroup = taskGroupMap.get(prevId);

        if (!decisionNodes.find((d) => d.id === decisionId)) {
          decisionNodes.push({
            id: decisionId,
            type: 'decisionNode',
            parentId: sourceGroup ?? undefined,
            extent: sourceGroup ? 'parent' as const : undefined,
            position: { x: 0, y: 0 },
            data: { when: whenExpr },
          });
          decisionTargetMap.set(decisionId, currId);

          pushPlainEdge(taskEdges, prevId, decisionId, `implicit-${prevId}-${decisionId}`, RAIL_MARKER, RAIL_STYLE);

          taskEdges.push({
            id: `yes-${decisionId}-${currId}`,
            source: decisionId,
            sourceHandle: 'yes',
            target: currId,
            type: 'smoothstep',
            animated: false,
            label: 'yes',
            labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#16A34A' },
            labelBgStyle: { fill: '#F0FDF4', fillOpacity: 1 },
            labelBgPadding: [2, 4] as [number, number],
            labelBgBorderRadius: 3,
            markerEnd: YES_MARKER,
            style: YES_STYLE,
          });
        }
      } else {
        pushPlainEdge(taskEdges, prevId, currId, `implicit-${prevId}-${currId}`, RAIL_MARKER, RAIL_STYLE);
      }
    }

    // === alt 边补全 ===
    // 对带 when 且没有任何出边的 task（显式 + 隐式边均未把它作为 source），
    // 补一条到 group.exit handle 的灰色虚线，label 为 'alt'。
    // group.exit 是 target handle（底部），与 group.bottom（source → END）同位置，
    // 视觉上形成 task → exit → END 的连接。
    const tasksWithOutgoing = new Set(taskEdges.map((e) => e.source));
    for (const taskId of taskWhenMap.keys()) {
      if (tasksWithOutgoing.has(taskId)) continue;
      const groupId = taskGroupMap.get(taskId);
      if (!groupId) continue;
      taskEdges.push({
        id: `alt-${taskId}-${groupId}`,
        source: taskId,
        target: groupId,
        targetHandle: 'exit',
        type: 'smoothstep',
        animated: false,
        label: 'alt',
        labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: ALT_LABEL_FILL },
        labelBgStyle: { fill: '#F1F5F9', fillOpacity: 1 },
        labelBgPadding: [2, 4] as [number, number],
        labelBgBorderRadius: 3,
        markerEnd: ALT_MARKER,
        style: ALT_STYLE,
      });
    }

    // === no 边构建 ===
    // 为每个决策节点的 "no" 路径添加边，表示条件为 false 时跳过条件任务后的流向。
    // 汇入 group.exit handle（底部 target），与 group.bottom（source → END）同位置，
    // 视觉上形成 decision.no → exit → END 的连接。
    for (const dn of decisionNodes) {
      const groupId = dn.parentId;
      if (!groupId) continue;
      taskEdges.push({
        id: `no-${dn.id}-${groupId}`,
        source: dn.id,
        sourceHandle: 'no',
        target: groupId,
        targetHandle: 'exit',
        type: 'smoothstep',
        animated: false,
        label: 'no',
        labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#64748B' },
        labelBgStyle: { fill: '#F1F5F9', fillOpacity: 1 },
        labelBgPadding: [2, 4] as [number, number],
        labelBgBorderRadius: 3,
        markerEnd: RAIL_MARKER,
        style: RAIL_STYLE,
      });
    }

    // 跨 subpipeline 边 —— 直接连接 group 节点（不经过 task），让 dagre 识别 group 拓扑顺序
    subpipelines.forEach((sub, idx) => {
      sub.depends_on?.forEach((depSubName) => {
        const sourceIdx = subpipelines.findIndex((s) => s.name === depSubName);
        if (sourceIdx >= 0 && sourceIdx < subpipelineTaskIds.length) {
          const sourceIds = subpipelineTaskIds[sourceIdx];
          const targetIds = subpipelineTaskIds[idx];
          if (sourceIds.length > 0 && targetIds.length > 0) {
            const targetId = targetIds[0];
            const sourceGroup = `__group__${depSubName}`;
            const targetGroup = `__group__${sub.name}`;
            const whenExpr = taskWhenMap.get(targetId);
            // 跨 group 拓扑边：sourceGroup.bottom → targetGroup.top（让 dagre 知道顺序）
            taskEdges.push({
              id: `cross-sub-${depSubName}-${sub.name}`,
              source: sourceGroup,
              sourceHandle: 'bottom',
              target: targetGroup,
              targetHandle: 'top',
              type: 'smoothstep',
              animated: false,
              markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#F59E0B' },
              style: { stroke: '#F59E0B', strokeWidth: 1.5, strokeDasharray: '4 3' },
            });
            if (whenExpr) {
              const decisionId = `decision-cross-${depSubName}-${sub.name}`;
              decisionNodes.push({
                id: decisionId,
                type: 'decisionNode',
                parentId: targetGroup,
                extent: 'parent' as const,
                position: { x: 0, y: 0 },
                data: { when: whenExpr },
              });
              decisionTargetMap.set(decisionId, targetId);
              // targetGroup.top-out → decision（灰色内部边）
              taskEdges.push({
                id: `enter-decision-${decisionId}`,
                source: targetGroup,
                sourceHandle: 'top-out',
                target: decisionId,
                type: 'smoothstep',
                animated: false,
                markerEnd: RAIL_MARKER,
                style: RAIL_STYLE,
              });
              taskEdges.push({
                id: `yes-${decisionId}-${targetId}`,
                source: decisionId,
                sourceHandle: 'yes',
                target: targetId,
                type: 'smoothstep',
                animated: false,
                label: 'yes',
                labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#16A34A' },
                labelBgStyle: { fill: '#F0FDF4', fillOpacity: 1 },
                labelBgPadding: [2, 4] as [number, number],
                labelBgBorderRadius: 3,
                markerEnd: YES_MARKER,
                style: YES_STYLE,
              });
            } else {
              // 无 when：targetGroup.top-out → 首 task（灰色内部边）
              taskEdges.push({
                id: `enter-${targetGroup}`,
                source: targetGroup,
                sourceHandle: 'top-out',
                target: targetId,
                type: 'smoothstep',
                animated: false,
                markerEnd: RAIL_MARKER,
                style: RAIL_STYLE,
              });
            }
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
            markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#94A3B8' },
            style: { stroke: '#CBD5E1', strokeWidth: 1.2, strokeDasharray: '3 3' },
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

    // === Start / End 哨兵节点（占位，位置在分组尺寸调整后设置） ===
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

    // 拓扑：START → group.top(IN) → group.top-out → 首 task → ... → 末 task → group.exit(OUT) → group.bottom → END
    // no/alt 边汇入 group.exit（底部 target handle），与 group.bottom（底部 source → END）同位置。
    const groupHasIncoming = new Set<string>();
    const groupHasOutgoing = new Set<string>();
    for (const e of taskEdges) {
      if (e.target === '__end__' || e.source === '__start__') continue;
      const srcTask = taskNodes.find((t) => t.id === e.source);
      const tgtTask = taskNodes.find((t) => t.id === e.target);
      const srcDecision = decisionNodes.find((d) => d.id === e.source);
      const tgtDecision = decisionNodes.find((d) => d.id === e.target);
      // 边两端可能是：task（parentId 即 group）、decisionNode（parentId 即 group）、或 group 本身
      const srcGroup = srcTask?.parentId ?? srcDecision?.parentId
        ?? (e.source.startsWith('__group__') ? e.source : null);
      const tgtGroup = tgtTask?.parentId ?? tgtDecision?.parentId
        ?? (e.target.startsWith('__group__') ? e.target : null);
      // 跨 group 的边才计入
      if (tgtGroup && srcGroup !== tgtGroup) {
        groupHasIncoming.add(tgtGroup);
      }
      if (srcGroup && srcGroup !== tgtGroup) {
        groupHasOutgoing.add(srcGroup);
      }
    }

    // 建立 group → 首/末 task 映射，用于 START/END 直连首/末 task
    const groupFirstTask = new Map<string, string>();
    const groupLastTask = new Map<string, string>();
    subpipelines.forEach((sub, idx) => {
      const groupId = `__group__${sub.name}`;
      const ids = subpipelineTaskIds[idx];
      if (ids.length > 0) {
        groupFirstTask.set(groupId, ids[0]);
        groupLastTask.set(groupId, ids[ids.length - 1]);
      }
    });

    const allGroupIds = groupNodes.map((n) => n.id);
    const rootGroupIds = allGroupIds.filter((id) => !groupHasIncoming.has(id));
    const leafGroupIds = allGroupIds.filter((id) => !groupHasOutgoing.has(id));

    const START_MARKER = { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#10B981' };
    const END_MARKER = { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#94A3B8' };
    for (const gid of rootGroupIds) {
      const firstTaskId = groupFirstTask.get(gid);
      // START → group.top（绿色，进入 group 的 IN handle）
      // group.top-out → 首 task 或 decision（灰色内部边，不穿出 group）
      if (firstTaskId) {
        const firstTaskWhen = taskWhenMap.get(firstTaskId);
        const decisionForFirstTask = firstTaskWhen
          ? decisionNodes.find((d) => d.parentId === gid && decisionTargetMap.get(d.id) === firstTaskId)
          : undefined;
        const enterTarget = decisionForFirstTask ? decisionForFirstTask.id : firstTaskId;

        // START → group.top（绿色外部边）
        taskEdges.push({
          id: `start-to-${gid}`,
          source: '__start__',
          target: gid,
          targetHandle: 'top',
          type: 'smoothstep',
          animated: false,
          markerEnd: START_MARKER,
          style: { stroke: '#10B981', strokeWidth: 1.5 },
        });
        // group.top-out → 首 task/decision（灰色内部边）
        taskEdges.push({
          id: `enter-${gid}`,
          source: gid,
          sourceHandle: 'top-out',
          target: enterTarget,
          type: 'smoothstep',
          animated: false,
          markerEnd: RAIL_MARKER,
          style: RAIL_STYLE,
        });
      } else {
        // 空 group 回退：START → group.top
        taskEdges.push({
          id: `start-to-${gid}`,
          source: '__start__',
          target: gid,
          targetHandle: 'top',
          type: 'smoothstep',
          animated: false,
          markerEnd: START_MARKER,
          style: { stroke: '#10B981', strokeWidth: 1.5 },
        });
      }
    }
    for (const gid of leafGroupIds) {
      const lastTaskId = groupLastTask.get(gid);
      // 末 task → group.exit（底部 target handle）
      // group.bottom（底部 source handle）→ END
      // exit 和 bottom 同位于底部，视觉上形成 末task → exit → END 连接
      if (lastTaskId) {
        taskEdges.push({
          id: `${gid}-out`,
          source: lastTaskId,
          target: gid,
          targetHandle: 'exit',
          type: 'smoothstep',
          animated: false,
          markerEnd: END_MARKER,
          style: { stroke: '#94A3B8', strokeWidth: 1.5 },
        });
        taskEdges.push({
          id: `${gid}-to-end`,
          source: gid,
          sourceHandle: 'bottom',
          target: '__end__',
          type: 'smoothstep',
          animated: false,
          markerEnd: END_MARKER,
          style: { stroke: '#94A3B8', strokeWidth: 1.5 },
        });
      } else {
        // 空 group 回退：group.bottom → END
        taskEdges.push({
          id: `${gid}-to-end`,
          source: gid,
          sourceHandle: 'bottom',
          target: '__end__',
          type: 'smoothstep',
          animated: false,
          markerEnd: END_MARKER,
          style: { stroke: '#94A3B8', strokeWidth: 1.5 },
        });
      }
    }
    if (allGroupIds.length === 0) {
      const taskHasIncoming = new Set(taskEdges.map((e) => e.target));
      const taskHasOutgoing = new Set(taskEdges.map((e) => e.source));
      const allTaskIds = taskNodes.map((n) => n.id);
      for (const tid of allTaskIds.filter((id) => !taskHasIncoming.has(id))) {
        taskEdges.push({
          id: `start-to-${tid}`,
          source: '__start__',
          target: tid,
          type: 'smoothstep',
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#10B981' },
          style: { stroke: '#10B981', strokeWidth: 1.5 },
        });
      }
      for (const tid of allTaskIds.filter((id) => !taskHasOutgoing.has(id))) {
        taskEdges.push({
          id: `${tid}-to-end`,
          source: tid,
          target: '__end__',
          type: 'smoothstep',
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#94A3B8' },
          style: { stroke: '#94A3B8', strokeWidth: 1.5 },
        });
      }
    }

    // dagre 布局
    // groupSizes 同时承载 group 与 decision 节点的自定义尺寸：
    // dagreLayout.getNodeSize 优先查 custom 尺寸，再回退到 type 硬编码。
    const groupSizes = new Map<string, { width: number; height: number }>();
    for (const gn of groupNodes) {
      const w = (gn.style as { width?: number })?.width ?? 200;
      const h = (gn.style as { height?: number })?.height ?? 100;
      groupSizes.set(gn.id, { width: w, height: h });
    }
    for (const dn of decisionNodes) {
      groupSizes.set(dn.id, { width: DECISION_SIZE, height: DECISION_SIZE });
    }

    const allNodes = [...groupNodes, ...taskNodes, ...decisionNodes, ...postNodes, startNode, endNode];
    const layoutedNodes = applyDagreLayout(allNodes, taskEdges, groupSizes);

    // 固定 Start 在最顶部
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

    // 调整 group 尺寸以包裹所有子节点
    for (const node of finalNodes) {
      if (node.type === 'subpipelineGroup') {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const child of finalNodes) {
          if (child.parentId === node.id) {
            const cw = child.type === 'postTask'
              ? POST_W
              : child.type === 'decisionNode'
                ? DECISION_SIZE
                : TASK_W;
            const ch = child.type === 'postTask'
              ? POST_H
              : child.type === 'decisionNode'
                ? DECISION_SIZE
                : TASK_H;
            minX = Math.min(minX, child.position.x);
            minY = Math.min(minY, child.position.y);
            maxX = Math.max(maxX, child.position.x + cw);
            maxY = Math.max(maxY, child.position.y + ch);
          }
        }
        if (minX < Infinity) {
          const dagreW = ((node.style as { width?: number })?.width) ?? 0;
          const contentW = maxX - minX + GROUP_PADDING_X * 2;
          const contentH = maxY - minY + GROUP_PADDING_Y * 2 + GROUP_HEADER + GROUP_ENTRY_AREA + GROUP_EXIT_AREA;
          node.style = {
            ...((node.style as object) || {}),
            width: Math.max(dagreW, contentW),
            height: contentH,
          };
          for (const child of finalNodes) {
            if (child.parentId === node.id) {
              child.position = {
                x: child.position.x - minX + GROUP_PADDING_X,
                y: child.position.y - minY + GROUP_PADDING_Y + GROUP_HEADER + GROUP_ENTRY_AREA,
              };
            }
          }
        }
      }
    }

    // 修复：dagre 用估算高度布局，group 实际高度更大 → 相邻 group 垂直重叠
    // 按 dagre 给的 y 排序，逐个下推消除重叠（仅处理 x 范围有重叠的 group 对）
    const sortedGroups = finalNodes
      .filter((n) => n.type === 'subpipelineGroup')
      .sort((a, b) => a.position.y - b.position.y);

    for (let i = 0; i < sortedGroups.length; i++) {
      const curr = sortedGroups[i];
      const currW = (curr.style as { width?: number })?.width ?? 200;
      for (let j = 0; j < i; j++) {
        const prev = sortedGroups[j];
        const prevW = (prev.style as { width?: number })?.width ?? 200;
        const prevH = (prev.style as { height?: number })?.height ?? 100;
        // x 范围无重叠则跳过（并行 group 不需下推）
        const xOverlap = !(curr.position.x + currW <= prev.position.x || prev.position.x + prevW <= curr.position.x);
        if (!xOverlap) continue;
        const prevBottom = prev.position.y + prevH;
        if (curr.position.y < prevBottom + GROUP_GAP_Y) {
          curr.position.y = prevBottom + GROUP_GAP_Y;
        }
      }
    }

    // End 定位到最底部
    let finalMaxY = -Infinity;
    for (const node of finalNodes) {
      if (node.id === '__start__' || node.id === '__end__') continue;
      const nodeBottom = node.position.y + ((node.type === 'subpipelineGroup')
        ? ((node.style as { height?: number })?.height ?? 100)
        : node.type === 'decisionNode'
          ? DECISION_SIZE
          : TASK_H);
      finalMaxY = Math.max(finalMaxY, nodeBottom);
    }
    if (!isFinite(finalMaxY)) finalMaxY = 100;
    for (const node of finalNodes) {
      if (node.id === '__end__') {
        node.position.y = finalMaxY + 60;
      }
    }

    // 对齐 __start__ / __end__ 的 x 到所连接 group 的中心，消除长水平飞线
    // START/END 现在直连首/末 task，需先找到该 task 所属 group 再居中
    const START_W = 66, END_W = 52;
    const findGroupOfNode = (nodeId: string | undefined) => {
      if (!nodeId) return undefined;
      const n = finalNodes.find((x) => x.id === nodeId);
      if (!n) return undefined;
      if (n.type === 'subpipelineGroup') return n;
      if (n.parentId) return finalNodes.find((x) => x.id === n.parentId);
      return undefined;
    };
    for (const node of finalNodes) {
      if (node.id === '__start__') {
        const startEdge = taskEdges.find((e) => e.source === '__start__');
        const targetGroup = findGroupOfNode(startEdge?.target);
        if (targetGroup) {
          const gw = ((targetGroup.style as { width?: number })?.width) ?? 200;
          node.position.x = targetGroup.position.x + gw / 2 - START_W / 2;
        }
      } else if (node.id === '__end__') {
        // END 对齐所连接 group 的中心。
        // 主出边（末 task → END，id 以 '-to-end' 结尾）决定 END 的 x；
        // alt 边汇入 group.exit（不直连 END），不影响 END 定位。
        const endEdge = taskEdges.find(
          (e) => e.target === '__end__' && e.id.endsWith('-to-end'),
        );
        const srcGroup = findGroupOfNode(endEdge?.source);
        if (srcGroup) {
          const gw = ((srcGroup.style as { width?: number })?.width) ?? 200;
          node.position.x = srcGroup.position.x + gw / 2 - END_W / 2;
        }
      }
    }

    return { nodes: finalNodes, edges: taskEdges };
  }, [pipeline, taskStatuses]);
}
