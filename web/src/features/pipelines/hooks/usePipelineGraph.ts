import { useMemo } from 'react';
import type { Node, Edge } from '@xyflow/react';
import type { PipelineDetail, TaskStatus, PostConfig } from '@/types';
import type { PostVariant } from '../nodes/PostTaskNode';
import { EDGE, INK, NODE_SIZE } from '../nodes/nodeTokens';
import { applyDagreLayout } from '@/utils/dagreLayout';

// v11 (2026-08): LR 流向语义 —— 常量从"垂直区域"翻转为"水平区域"：
//   ENTRY/EXIT 从上下预留区变为左右预留区（入口线从左缘进、出口线从右缘出）
const GROUP_PADDING_X = 20;
const GROUP_PADDING_Y = 14;
/** 组间水平间距（原 GROUP_GAP_Y 垂直间距的 LR 对应物） */
const GROUP_GAP_X = 32;
// 分组 header 行（名称/策略/任务数）占位高度（仍在顶部）
const GROUP_HEADER = 30;
// 左侧入口区：top-out handle → 首 task/decision 的边需要水平空间
const GROUP_ENTRY_W = 36;
// 右侧出口区：no/alt/lastTask 边汇聚到 exit handle 需要水平空间
const GROUP_EXIT_W = 48;
// 尺寸统一引用 nodeTokens.NODE_SIZE（v11 任务卡 200×56）
const TASK_W = NODE_SIZE.TASK_W;
const TASK_H = NODE_SIZE.TASK_H;
const POST_H = 26;
const POST_W = 168;
/** v11: 与 DecisionNode 新尺寸一致（64，原 76） */
const DECISION_SIZE = 64;
/** post 子节点与父任务的垂直间距（post 挂在父任务正下方） */
const POST_GAP_Y = 8;

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

/** 默认流轨样式
 * v5 (2026-08): 从硬编码色值迁移到 nodeTokens.EDGE 统一管理
 * v11 (2026-08): 箭头退役（n8n 画布无箭头，流向由 LR 布局表达）
 */
const RAIL_STYLE = { stroke: EDGE.rail.stroke, strokeWidth: EDGE.rail.strokeWidth };

/**
 * v11 (2026-08): 连线路由 —— LR 流向下 bezier（type:'default'）才是"顺流"曲线。
 * v10 弃用 bezier 的根因是垂直流向 + 水平偏移画出下垂 S 弯；方向翻转后
 * bezier 控制点沿水平方向伸展，恰好是 n8n 的标志性流线。
 */
const EDGE_TYPE = 'default' as const;

/** Yes 路径边样式（绿色实线，语义：条件成立执行） */
const YES_STYLE = { stroke: EDGE.yes.stroke, strokeWidth: EDGE.yes.strokeWidth };

/** alt 路径边样式（浅灰实线，虚线已退役 —— n8n 画布无虚线，语义靠明度区分） */
const ALT_STYLE = { stroke: EDGE.railSoft.stroke, strokeWidth: EDGE.railSoft.strokeWidth };
// v5 (2026-08): label 文字色统一引用 INK.textSecondary，白底可读
const ALT_LABEL_FILL = INK.textSecondary;

function pushPlainEdge(
  taskEdges: Edge[],
  sourceId: string,
  targetId: string,
  edgeBaseId: string,
) {
  taskEdges.push({
    id: edgeBaseId,
    source: sourceId,
    target: targetId,
    type: EDGE_TYPE,
    animated: false,
    style: RAIL_STYLE,
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
    // 收集所有有效 taskId，用于校验 depends_on 引用的 source 是否存在
    const validTaskIds = new Set<string>();

    subpipelines.forEach((sub) => {
      const ids: string[] = [];
      const groupId = `__group__${sub.name}`;

      sub.tasks?.forEach((task) => {
        const taskId = `${sub.name}.${task.name}`;
        validTaskIds.add(taskId);
        const status = taskStatuses?.[taskId];
        const whenExpr = task.when?.trim();

        taskNodes.push({
          id: taskId,
          type: 'taskNode',
          parentId: groupId,
          extent: 'parent' as const,
          position: { x: 0, y: 0 },
          // v6 (2026-08): 顶层显式尺寸 —— MiniMap nodeHasDimensions 依赖（受控模式无测量回写）
          width: TASK_W,
          height: TASK_H,
          data: { task, subpipelineName: sub.name, status, order: orderIndex },
        });
        orderIndex++;
        ids.push(taskId);

        if (whenExpr) {
          taskWhenMap.set(taskId, whenExpr);
        }

        // 收集显式 depends_on（跳过引用不存在 task 的孤儿边，避免 dagre 崩溃）
        task.depends_on?.forEach((dep) => {
          const sourceId = `${sub.name}.${dep}`;
          if (!validTaskIds.has(sourceId)) return;
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
      // v11 (LR): 组尺寸估算 —— 宽 = 任务链横向长度（含入口/出口区），
      // 高 = 单行任务高 + post 悬挂行（dagre 估算用，wrap 阶段按实际子节点收紧）
      const rowH = Math.max(TASK_H + 20, DECISION_SIZE + 20);
      const taskChainW = ids.length > 0
        ? ids.length * TASK_W + Math.max(0, ids.length - 1) * 60
        : 0;
      const postRows = postCount > 0 ? postCount * (POST_H + 6) + 6 : 0;
      // v6 (2026-08): group 尺寸同时写顶层 width/height 与 style —— MiniMap 读顶层值
      const headerW = Math.ceil(sub.name.length * 7.5) + 110 + 24;
      const initW = hasChildren
        ? Math.max(taskChainW, headerW) + GROUP_PADDING_X * 2 + GROUP_ENTRY_W + GROUP_EXIT_W
        : Math.max(200, headerW + GROUP_PADDING_X * 2);
      const initH = rowH + postRows + GROUP_PADDING_Y * 2 + GROUP_HEADER * 2;
      groupNodes.push({
        id: groupId,
        type: 'subpipelineGroup',
        position: { x: 0, y: 0 },
        width: initW,
        height: initH,
        style: {
          width: initW,
          height: initH,
        },
        data: {
          label: sub.name,
          taskCount: ids.length,
          // v7 (2026-08): header 行策略徽章
          strategy:
            sub.config?.execution_strategy
            ?? pipeline.options?.execution_strategy
            ?? pipeline.config?.execution_strategy
            ?? 'sequential',
        },
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
              width: DECISION_SIZE,
              height: DECISION_SIZE,
              data: { when: whenExpr },
            });
            decisionTargetMap.set(decisionId, targetId);

            // source → decision
            pushPlainEdge(taskEdges, sourceId, decisionId, `dep-${sourceId}-${decisionId}`);

            // decision → (yes) → 条件任务
            taskEdges.push({
              id: `yes-${decisionId}-${targetId}`,
              source: decisionId,
              sourceHandle: 'yes',
              target: targetId,
              type: EDGE_TYPE,
              animated: false,
              label: 'yes',
              labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#15803D' },
              labelBgStyle: { fill: '#F0FDF4', fillOpacity: 1 },
              labelBgPadding: [2, 4] as [number, number],
              labelBgBorderRadius: 3,
              style: YES_STYLE,
            });

            // no 路径由菱形标注隐含（不画边，避免交叉）
          }
        } else {
          pushPlainEdge(taskEdges, sourceId, targetId, `dep-${sourceId}-${targetId}`);
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
            width: DECISION_SIZE,
            height: DECISION_SIZE,
            data: { when: whenExpr },
          });
          decisionTargetMap.set(decisionId, currId);

          pushPlainEdge(taskEdges, prevId, decisionId, `implicit-${prevId}-${decisionId}`);

          taskEdges.push({
            id: `yes-${decisionId}-${currId}`,
            source: decisionId,
            sourceHandle: 'yes',
            target: currId,
            type: EDGE_TYPE,
            animated: false,
            label: 'yes',
            labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#15803D' },
            labelBgStyle: { fill: '#F0FDF4', fillOpacity: 1 },
            labelBgPadding: [2, 4] as [number, number],
            labelBgBorderRadius: 3,
            style: YES_STYLE,
          });
        }
      } else {
        pushPlainEdge(taskEdges, prevId, currId, `implicit-${prevId}-${currId}`);
      }
    }

    // === alt 边补全 ===
    // 对带 when 且没有任何出边的 task，补一条到 group.exit handle 的浅灰实线，
    // label 为 'alt'。group.exit 是 target handle（右缘），与 group.bottom（source → END）
    // 同位置，视觉上形成 task → exit → END 的连接。
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
        type: EDGE_TYPE,
        animated: false,
        label: 'alt',
        labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: ALT_LABEL_FILL },
        labelBgStyle: { fill: '#F8FAFC', fillOpacity: 1 },
        labelBgPadding: [2, 4] as [number, number],
        labelBgBorderRadius: 3,
        style: ALT_STYLE,
      });
    }

    // === no 边构建 ===
    // 为每个决策节点的 "no" 路径添加边（菱形底部出），汇入 group.exit（右缘 target），
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
        type: EDGE_TYPE,
        animated: false,
        label: 'no',
        labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: INK.textSecondary },
        labelBgStyle: { fill: '#F8FAFC', fillOpacity: 1 },
        labelBgPadding: [2, 4] as [number, number],
        labelBgBorderRadius: 3,
        style: RAIL_STYLE,
      });
    }

    // 跨 subpipeline 边 —— 直接连接 group 节点（不经过 task），让 dagre 识别 group 拓扑顺序
    const enterEdgeCreated = new Set<string>();
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
            // 跨 group 拓扑边：sourceGroup.bottom(右缘) → targetGroup.top(左缘)
            taskEdges.push({
              id: `cross-sub-${depSubName}-${sub.name}`,
              source: sourceGroup,
              sourceHandle: 'bottom',
              target: targetGroup,
              targetHandle: 'top',
              type: EDGE_TYPE,
              animated: false,
              style: { stroke: EDGE.cross.stroke, strokeWidth: EDGE.cross.strokeWidth },
            });
            if (whenExpr) {
              const decisionId = `decision-cross-${depSubName}-${sub.name}`;
              decisionNodes.push({
                id: decisionId,
                type: 'decisionNode',
                parentId: targetGroup,
                extent: 'parent' as const,
                position: { x: 0, y: 0 },
                width: DECISION_SIZE,
                height: DECISION_SIZE,
                data: { when: whenExpr },
              });
              decisionTargetMap.set(decisionId, targetId);
              // targetGroup.top-out(左缘) → decision（灰色内部边）
              taskEdges.push({
                id: `enter-decision-${decisionId}`,
                source: targetGroup,
                sourceHandle: 'top-out',
                target: decisionId,
                type: EDGE_TYPE,
                animated: false,
                style: RAIL_STYLE,
              });
              taskEdges.push({
                id: `yes-${decisionId}-${targetId}`,
                source: decisionId,
                sourceHandle: 'yes',
                target: targetId,
                type: EDGE_TYPE,
                animated: false,
                label: 'yes',
                labelStyle: { fontFamily: 'ui-monospace, monospace', fontSize: 9, fontWeight: 600, fill: '#15803D' },
                labelBgStyle: { fill: '#F0FDF4', fillOpacity: 1 },
                labelBgPadding: [2, 4] as [number, number],
                labelBgBorderRadius: 3,
                style: YES_STYLE,
              });
            } else if (!enterEdgeCreated.has(targetGroup)) {
              // 无 when：targetGroup.top-out → 首 task（灰色内部边，每个 targetGroup 只创建一次）
              taskEdges.push({
                id: `enter-${targetGroup}`,
                source: targetGroup,
                sourceHandle: 'top-out',
                target: targetId,
                type: EDGE_TYPE,
                animated: false,
                style: RAIL_STYLE,
              });
              enterEdgeCreated.add(targetGroup);
            }
          }
        }
      });
    });

    // === Post 阶段节点 ===
    // v11 (LR): post 节点不进入 dagre（LR 会把子节点排到父任务右侧主流程道上，
    // 与主流混淆）—— 布局后手工挂到父任务正下方，像"脚注"一样垂直堆叠
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
            width: POST_W,
            height: POST_H,
            data: { label: pt.name, variant, parentTaskId },
          });
          taskEdges.push({
            id: `post-edge-${parentTaskId}-${postId}`,
            source: parentTaskId,
            target: postId,
            type: EDGE_TYPE,
            animated: false,
            style: { stroke: EDGE.railSoft.stroke, strokeWidth: EDGE.railSoft.strokeWidth },
          });
        }
      }
    }

    subpipelines.forEach((sub, idx) => {
      const groupId = `__group__${sub.name}`;
      const lastTaskId = subpipelineTaskIds[idx]?.[subpipelineTaskIds[idx].length - 1];
      // subpipeline 级 post 需要挂在最后一个 task 上；空 subpipeline 无 task 可挂，跳过
      if (lastTaskId) {
        addPostNodes(sub.post, lastTaskId, groupId);
      }
      sub.tasks?.forEach((task) => {
        addPostNodes(task.post, `${sub.name}.${task.name}`, groupId);
      });
    });

    // === Start / End 哨兵节点（占位，位置在分组尺寸调整后设置） ===
    // v11 (2026-08): trigger 式节点卡片（非圆形），LR 流向上 START 在最左、END 在最右
    const startNode: Node = {
      id: '__start__',
      type: 'startEnd',
      position: { x: 0, y: 0 },
      width: NODE_SIZE.SENTINEL_START_W,
      height: NODE_SIZE.SENTINEL_H,
      data: { variant: 'start' },
    };
    const endNode: Node = {
      id: '__end__',
      type: 'startEnd',
      position: { x: 0, y: 0 },
      width: NODE_SIZE.SENTINEL_END_W,
      height: NODE_SIZE.SENTINEL_H,
      data: { variant: 'end' },
    };

    // 拓扑：START → group.top(左缘) → group.top-out → 首 task → ... → 末 task → group.exit(右缘) → group.bottom → END
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

    for (const gid of rootGroupIds) {
      const firstTaskId = groupFirstTask.get(gid);
      // START → group.top（绿色，进入 group 左缘 IN handle）
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
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.start.stroke, strokeWidth: EDGE.start.strokeWidth },
        });
        // group.top-out → 首 task/decision（灰色内部边）
        taskEdges.push({
          id: `enter-${gid}`,
          source: gid,
          sourceHandle: 'top-out',
          target: enterTarget,
          type: EDGE_TYPE,
          animated: false,
          style: RAIL_STYLE,
        });
      } else {
        // 空 group 回退：START → group.top
        taskEdges.push({
          id: `start-to-${gid}`,
          source: '__start__',
          target: gid,
          targetHandle: 'top',
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.start.stroke, strokeWidth: EDGE.start.strokeWidth },
        });
      }
    }
    for (const gid of leafGroupIds) {
      const lastTaskId = groupLastTask.get(gid);
      // 末 task → group.exit（右缘 target handle）
      // group.bottom（右缘 source handle）→ END
      if (lastTaskId) {
        taskEdges.push({
          id: `${gid}-out`,
          source: lastTaskId,
          target: gid,
          targetHandle: 'exit',
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.end.stroke, strokeWidth: EDGE.end.strokeWidth },
        });
        taskEdges.push({
          id: `${gid}-to-end`,
          source: gid,
          sourceHandle: 'bottom',
          target: '__end__',
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.end.stroke, strokeWidth: EDGE.end.strokeWidth },
        });
      } else {
        // 空 group 回退：group.bottom → END
        taskEdges.push({
          id: `${gid}-to-end`,
          source: gid,
          sourceHandle: 'bottom',
          target: '__end__',
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.end.stroke, strokeWidth: EDGE.end.strokeWidth },
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
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.start.stroke, strokeWidth: EDGE.start.strokeWidth },
        });
      }
      for (const tid of allTaskIds.filter((id) => !taskHasOutgoing.has(id))) {
        taskEdges.push({
          id: `${tid}-to-end`,
          source: tid,
          target: '__end__',
          type: EDGE_TYPE,
          animated: false,
          style: { stroke: EDGE.end.stroke, strokeWidth: EDGE.end.strokeWidth },
        });
      }
    }

    // dagre 布局
    // groupSizes 同时承载 group 与 decision 节点的自定义尺寸
    const groupSizes = new Map<string, { width: number; height: number }>();
    for (const gn of groupNodes) {
      const w = (gn.style as { width?: number })?.width ?? 200;
      const h = (gn.style as { height?: number })?.height ?? 100;
      groupSizes.set(gn.id, { width: w, height: h });
    }
    for (const dn of decisionNodes) {
      groupSizes.set(dn.id, { width: DECISION_SIZE, height: DECISION_SIZE });
    }

    // v11 (LR): post 节点不进 dagre —— LR 会把子节点排到父任务右侧主流程道上，
    // 与主流混淆；post 边也不参与排序（dagre 对未知节点会崩溃）。
    // 布局后 post 手工挂到父任务正下方。
    const postNodeIds = new Set(postNodes.map((n) => n.id));
    const dagreNodes = [...groupNodes, ...taskNodes, ...decisionNodes, startNode, endNode];
    const dagreEdges = taskEdges.filter((e) => !postNodeIds.has(e.target));
    const layoutedNodes = applyDagreLayout(dagreNodes, dagreEdges, groupSizes);

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

    // post 节点挂到父任务正下方（相对坐标已就绪，此时插入 finalNodes）
    // 同一父任务的多个 post 按声明顺序垂直堆叠
    {
      const postCounter = new Map<string, number>();
      for (const pn of postNodes) {
        const parentTaskId = (pn.data as { parentTaskId?: string }).parentTaskId;
        const parentTask = finalNodes.find((n) => n.id === parentTaskId);
        if (!parentTask) continue;
        const idx = postCounter.get(parentTaskId) ?? 0;
        postCounter.set(parentTaskId, idx + 1);
        pn.position = {
          x: parentTask.position.x,
          y: parentTask.position.y + TASK_H + POST_GAP_Y + idx * (POST_H + 6),
        };
        finalNodes.push(pn);
      }
    }

    // v11 (LR): 组内单链水平对齐 —— 链中段任务共享同一 Y（同一"泳道"直线贯穿）。
    // 为什么只对齐"严格链中段"节点（唯一前驱、且前驱的唯一出边指向自己）：
    //   分叉叶子/汇合点/多链头承载分支拓扑，强制对齐会让分支挤在同一行不可读。
    // 为什么放在相对坐标转换之后：此时 position 是组内相对坐标，
    //   后续"调整 group 尺寸以包裹所有子节点"会按对齐后的位置收紧组尺寸。
    const alignChainTasksInGroup = (nodes: Node[], edges: Edge[]) => {
      const inEdges = new Map<string, string[]>(); // target → sources（仅 task↔task 边）
      const outDeg = new Map<string, number>();
      for (const e of edges) {
        if (e.source.startsWith('__group__') || e.target.startsWith('__group__')) continue;
        if (e.source === '__start__' || e.target === '__end__') continue;
        if (!inEdges.has(e.target)) inEdges.set(e.target, []);
        inEdges.get(e.target)!.push(e.source);
        outDeg.set(e.source, (outDeg.get(e.source) ?? 0) + 1);
      }
      const byGroup = new Map<string, Node[]>();
      for (const n of nodes) {
        // decision 纳入对齐 —— when 条件链（task → decision → task）中菱形若不与任务
        // 同行，入边会形成 Z 字绕行。no/alt 边以 __group__ 为 target 已被过滤，
        // decision 的有效出边只剩 yes，满足"一进一出"条件时可安全对齐。
        if ((n.type !== 'taskNode' && n.type !== 'decisionNode') || !n.parentId) continue;
        if (!byGroup.has(n.parentId)) byGroup.set(n.parentId, []);
        byGroup.get(n.parentId)!.push(n);
      }
      for (const tasks of byGroup.values()) {
        if (tasks.length < 2) continue;
        // 基准 y：优先取链头任务的 y；无链头任务时（cross-sub 首任务带 when，
        // enter-decision 边被过滤）回退到任意入度为 0 的节点（即入口 decision）
        const head =
          tasks.find((t) => t.type === 'taskNode' && (inEdges.get(t.id)?.length ?? 0) === 0) ??
          tasks.find((t) => (inEdges.get(t.id)?.length ?? 0) === 0);
        if (!head) continue; // 无链头（纯并行/环）不对齐
        const baseY = head.position.y;
        for (const t of tasks) {
          if (t.id === head.id) continue;
          const preds = inEdges.get(t.id) ?? [];
          if (preds.length !== 1) continue; // 汇合点不对齐
          if ((outDeg.get(preds[0]) ?? 0) !== 1) continue; // 前驱分叉 → 本节点是分支叶，不对齐
          if ((outDeg.get(t.id) ?? 0) > 1) continue; // 自身分叉不对齐
          t.position.y = baseY;
        }
      }
    };
    alignChainTasksInGroup(finalNodes, taskEdges);

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
          // v11 (LR): contentW 含左入口区 + 右出口区；
          // contentH = 顶 header + 底对称区（header 同高）+ padding：
          // 上下对称的布局让链的垂直中轴 = 组 handle 中轴（top:50%），
          // enter/exit 边才是纯水平直线（header 独占顶部会下拉链中轴）
          const contentW = maxX - minX + GROUP_PADDING_X * 2 + GROUP_ENTRY_W + GROUP_EXIT_W;
          const contentH = maxY - minY + GROUP_PADDING_Y * 2 + GROUP_HEADER * 2;
          // v6 (2026-08): 顶层 width/height 与 style 同步更新（MiniMap 读顶层值）
          node.width = Math.max(dagreW, contentW);
          node.height = contentH;
          node.style = {
            ...((node.style as object) || {}),
            width: node.width,
            height: node.height,
          };
          // v11 (LR): 子节点定位 —— x 贴左（入口区之后），
          // y = 顶区（PAD + header）起排；顶底对称使链中轴 = handle 中轴
          const postStack = new Map<string, number>();
          for (const child of finalNodes) {
            if (child.parentId === node.id && child.type !== 'postTask') {
              child.position = {
                x: child.position.x - minX + GROUP_PADDING_X + GROUP_ENTRY_W,
                y: child.position.y - minY + GROUP_PADDING_Y + GROUP_HEADER,
              };
            } else if (child.parentId === node.id && child.type === 'postTask') {
              // post 跟随其父任务的新位置（post 保持悬挂堆叠）
              const parentTaskId = (child.data as { parentTaskId?: string }).parentTaskId;
              const parentTask = finalNodes.find((n) => n.id === parentTaskId);
              if (parentTask) {
                const idx = postStack.get(parentTaskId) ?? 0;
                postStack.set(parentTaskId, idx + 1);
                child.position = {
                  x: parentTask.position.x,
                  y: parentTask.position.y + TASK_H + POST_GAP_Y + idx * (POST_H + 6),
                };
              }
            }
          }
        }
      }
    }

    // 修复：dagre 用估算尺寸布局，group 实际尺寸更大 → 相邻 group 重叠
    // v11 (LR): 按 x 排序，逐个右推消除重叠（仅处理 y 范围有重叠的 group 对）
    const sortedGroups = finalNodes
      .filter((n) => n.type === 'subpipelineGroup')
      .sort((a, b) => a.position.x - b.position.x);

    for (let i = 0; i < sortedGroups.length; i++) {
      const curr = sortedGroups[i];
      const currH = (curr.style as { height?: number })?.height ?? 100;
      for (let j = 0; j < i; j++) {
        const prev = sortedGroups[j];
        const prevH = (prev.style as { height?: number })?.height ?? 100;
        const prevW = (prev.style as { width?: number })?.width ?? 200;
        // y 范围无重叠则跳过（同列并行 group 不需右推）
        const yOverlap = !(curr.position.y + currH <= prev.position.y || prev.position.y + prevH <= curr.position.y);
        if (!yOverlap) continue;
        const prevRight = prev.position.x + prevW;
        if (curr.position.x < prevRight + GROUP_GAP_X) {
          curr.position.x = prevRight + GROUP_GAP_X;
        }
      }
    }

    // v5 → v11 (LR): 组间拓扑右推 —— cross-sub 依赖边的下游组左缘不得在上游组右缘左侧。
    // 多轮迭代处理链式依赖（A→B→C 中右推 A 会连锁推 B）。
    {
      const groupDepEdges: [string, string][] = [];
      for (const e of taskEdges) {
        if (e.source.startsWith('__group__') && e.target.startsWith('__group__')) {
          groupDepEdges.push([e.source, e.target]);
        }
      }
      if (groupDepEdges.length > 0) {
        const nodeMap = new Map(finalNodes.map((n) => [n.id, n]));
        for (let round = 0; round < sortedGroups.length; round++) {
          let moved = false;
          for (const [srcId, tgtId] of groupDepEdges) {
            const s = nodeMap.get(srcId);
            const t = nodeMap.get(tgtId);
            if (!s || !t) continue;
            const sW = (s.style as { width?: number })?.width ?? 200;
            // 下游 left 至少在上游 right + GAP 之右，留出连线呼吸空间
            const minLeft = s.position.x + sW + GROUP_GAP_X;
            if (t.position.x < minLeft) {
              t.position.x = minLeft;
              moved = true;
            }
          }
          if (!moved) break;
        }
      }
    }

    // v11 (LR): START/END 定位 —— START 在所有 root group 联合包围盒左侧居中，
    // END 在所有 leaf group 联合包围盒右侧居中（并行多组时进出线对称汇入，交叉最少）。
    const jointBBoxOfGroups = (gids: string[]): { minX: number; minY: number; maxX: number; maxY: number } | undefined => {
      if (gids.length === 0) return undefined;
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const gid of gids) {
        const g = finalNodes.find((n) => n.id === gid);
        if (!g) continue;
        const gw = ((g.style as { width?: number })?.width) ?? 200;
        const gh = ((g.style as { height?: number })?.height) ?? 100;
        minX = Math.min(minX, g.position.x);
        minY = Math.min(minY, g.position.y);
        maxX = Math.max(maxX, g.position.x + gw);
        maxY = Math.max(maxY, g.position.y + gh);
      }
      if (!isFinite(minX)) return undefined;
      return { minX, minY, maxX, maxY };
    };
    // 哨兵与组之间的水平呼吸空间（给贝塞尔曲线留弯道）
    const SENTINEL_GAP_X = 72;
    for (const node of finalNodes) {
      if (node.id === '__start__') {
        const bbox = jointBBoxOfGroups(rootGroupIds);
        if (bbox) {
          node.position.x = bbox.minX - NODE_SIZE.SENTINEL_START_W - SENTINEL_GAP_X;
          node.position.y = (bbox.minY + bbox.maxY) / 2 - NODE_SIZE.SENTINEL_H / 2;
        }
      } else if (node.id === '__end__') {
        const bbox = jointBBoxOfGroups(leafGroupIds);
        if (bbox) {
          node.position.x = bbox.maxX + SENTINEL_GAP_X;
          node.position.y = (bbox.minY + bbox.maxY) / 2 - NODE_SIZE.SENTINEL_H / 2;
        }
      }
    }

    return { nodes: finalNodes, edges: taskEdges };
  }, [pipeline, taskStatuses]);
}
