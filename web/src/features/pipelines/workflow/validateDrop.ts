import type { Node } from '@xyflow/react';
import type { EditorNodeData } from './yamlToNodes';

/**
 * handleDrop 容器嵌套校验规则
 *
 * 校验规则（共 6 条）:
 *   R1: SubPipeline 不可嵌套 SubPipeline（拖入 SubPipeline 内部时拒绝）
 *   R2: Post 父容器仅可在根层级（不可拖入 SubPipeline/Task 内部）
 *   R3: Post 子容器各类型（on_fail/on_success/always）最多 1 个（若已存在则拒绝）
 *   R4: Post 子容器不可嵌套其它容器
 *   R5: 原子行为节点不可直接放入 SubPipeline 根层级（必须通过 Task）
 *   R6: 画布必须有且仅有一个 Start 和一个 End 节点
 *
 * @param nodeType - 被拖入节点的类型（来自 NodePalette 的 nodeType 字段）
 * @param parentContext - 目标落点上下文：'canvas-root'(画布根级) | 'subpipeline'(SubPipeline内部) | 'post_parent'(Post父容器内部)
 * @param existingNodes - 当前画布上已有的节点列表（用于检查重复约束）
 * @returns null 表示通过校验，string 返回不通过的原因（用于 toast/alert 显示）
 */

export type DropContext = 'canvas-root' | 'subpipeline' | 'post_parent';

/**
 * v3 (2026-07): 递归计算节点的绝对画布坐标。
 *
 * 为什么需要：ReactFlow 中带 parentId 的子节点 position 是“相对父容器”的，
 * 而非绝对画布坐标。多层嵌套时（如 SubPipeline 内再放 SubPipeline），
 * 子节点的 position 只相对其直接父容器。若不换算为绝对坐标，直接用落点的
 * 绝对 flowPosition 与节点的（相对）position 做 bounds 比较会错位，
 * 导致落点落在嵌套容器内部却被漏判为 canvas-root，R1（SubPipeline 不可嵌套）因此失效。
 * 这里沿 parentId 链递归累加父节点 position 得到绝对坐标。
 */
export function getAbsolutePosition(
  node: Node<EditorNodeData>,
  nodes: Node<EditorNodeData>[],
): { x: number; y: number } {
  let { x, y } = node.position;
  let current: Node<EditorNodeData> | undefined = node.parentId
    ? nodes.find((n) => n.id === node.parentId)
    : undefined;
  while (current) {
    x += current.position.x;
    y += current.position.y;
    current = current.parentId
      ? nodes.find((n) => n.id === current!.parentId)
      : undefined;
  }
  return { x, y };
}

/**
 * v2 (2026-07): 根据 drop 位置动态计算 parentContext
 * 通过检查 drop 的 flowPosition 是否落在某个容器节点内部来决定目标上下文
 *
 * 为什么不用 getIntersectingNodes: ReactFlowInstance.getIntersectingNodes 类型不稳定，
 * 手动遍历节点进行 bounds 检查更可控，且不依赖内部 API
 *
 * @returns { context: DropContext, parentId?: string } - 上下文和容器节点 id
 */
export function findDropParentContext(
  flowPosition: { x: number; y: number },
  nodes: Node<EditorNodeData>[],
): { context: DropContext; parentId?: string } {
  for (const node of nodes) {
    const w = node.width;
    const h = node.height;
    // 节点未完成测量（首次渲染），跳过
    if (!w || !h) continue;

    // 注意(2026-07): 嵌套子节点 position 是相对父容器的，必须先换算为绝对画布坐标，
    // 才能与已转成绝对坐标的 flowPosition 做正确的 bounds 比较。
    const absPos = getAbsolutePosition(node, nodes);

    const isInside =
      flowPosition.x >= absPos.x &&
      flowPosition.x <= absPos.x + w &&
      flowPosition.y >= absPos.y &&
      flowPosition.y <= absPos.y + h;

    if (!isInside) continue;

    if (node.type === 'editorSubPipeline') {
      return { context: 'subpipeline', parentId: node.id };
    }
    if (node.type === 'editorPostParent') {
      return { context: 'post_parent', parentId: node.id };
    }
    // editorTask / editorPostChild 等非容器节点忽略
  }
  return { context: 'canvas-root' };
}

export function validateDrop(
  nodeType: string,
  parentContext: DropContext,
  existingNodes: Node<EditorNodeData>[],
): string | null {
  // R2: Post 父容器仅可在根层级
  if (nodeType === 'post_parent') {
    if (parentContext !== 'canvas-root') {
      return 'Post 父容器仅可放置在根层级（不可拖入 SubPipeline 或 Task 内部）';
    }
  }

  // R1: SubPipeline 不可嵌套 SubPipeline
  if (nodeType === 'subpipeline' && parentContext === 'subpipeline') {
    return 'SubPipeline 不可嵌套在另一个 SubPipeline 内部';
  }

  // R4: Post 子容器不可嵌套其它容器 — 任何容器类型拖入 post_parent 都拒绝
  if (parentContext === 'post_parent') {
    // 仅 post_child 类型可以放入 Post 父容器
    const allowedInPost = ['post_child'];
    const isContainerType = ['subpipeline', 'task', 'post_parent'].includes(nodeType) ||
      (nodeType.startsWith('task_atomic_') && !allowedInPost.includes(nodeType));
    if (!allowedInPost.some(t => nodeType.startsWith(t))) {
      return 'Post 子容器内部不可嵌套其它容器节点';
    }
  }

  // R5: 原子行为节点不可直接放入 SubPipeline 根层级
  if (parentContext === 'subpipeline') {
    const atomicTypes = ['task_atomic_cmd', 'task_atomic_step', 'task_atomic_plugin', 'task_atomic_invoke'];
    if (atomicTypes.includes(nodeType)) {
      return '原子行为节点不可直接放入 SubPipeline 根层级（必须通过 Task 容器）';
    }
    // 只允许 post_parent 和 task 类型的容器放入 SubPipeline
    if (!['task', 'post_parent', 'post_child'].includes(nodeType)) {
      return `${nodeType} 类型不可放入 SubPipeline 内部`;
    }
  }

  // R3: Post 子容器各类型最多 1 个（在 Post 父容器内部时校验）
  if (nodeType === 'post_child_on_fail') {
    const exists = existingNodes.some(
      n => n.type === 'editorPostChild' && n.data?.postVariant === 'on_fail',
    );
    if (exists) return 'Post 子容器 on_fail 已存在，每种类型最多 1 个';
  }
  if (nodeType === 'post_child_on_success') {
    const exists = existingNodes.some(
      n => n.type === 'editorPostChild' && n.data?.postVariant === 'on_success',
    );
    if (exists) return 'Post 子容器 on_success 已存在，每种类型最多 1 个';
  }
  if (nodeType === 'post_child_always') {
    const exists = existingNodes.some(
      n => n.type === 'editorPostChild' && n.data?.postVariant === 'always',
    );
    if (exists) return 'Post 子容器 always 已存在，每种类型最多 1 个';
  }

  // R6: 画布必须有且仅有一个 Start 和一个 End（仅 canvas-root 上下文时校验）
  if (parentContext === 'canvas-root') {
    if (nodeType === 'startend') {
      const hasStart = existingNodes.some(n => n.id === '__start__');
      const hasEnd = existingNodes.some(n => n.id === '__end__');
      if (hasStart && hasEnd) {
        return '画布上已有 Start 和 End 节点（各仅需一个）';
      }
      // 允许补充缺失的一个
    }
  }

  return null; // 通过
}
