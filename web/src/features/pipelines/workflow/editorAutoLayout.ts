import type { Node, Edge } from '@xyflow/react';
import { applyDagreLayout } from '@/utils/dagreLayout';
import { EDITOR_LAYOUT, type EditorNodeData, type EditorEdgeData } from './yamlToNodes';

const ROOT = '__pipeline__';

/**
 * 编辑器自动布局（点击工具栏"布局/dagre"按钮触发）
 *
 * 根因修复（用户反馈：点击 dagre 后画布"乱成一团"）：
 * 旧实现把【所有节点】（含带 parentId 的嵌套子节点：subpipeline 内的 task、
 * Post 父容器内的 post 子节点）一股脑喂给 dagre。dagre 对父子层级一无所知，
 * 且 task 与它的容器之间并不存在连线，于是 dagre 把子节点散射到画布任意处；
 * 之后仅做一次"绝对坐标 - 父绝对坐标"的单层换算，得到的相对偏移往往极大，
 * 子节点便飞到容器之外 → 视觉混乱。
 *
 * 本实现的分层策略：
 *   1. 仅把【顶层容器图】（无 parentId 或 parentId===ROOT 的节点，外加 start/end）
 *      交给 dagre 排布，得到宏观拓扑（subpipeline 横排、跨组依赖有序）。
 *   2. 嵌套子节点（task / post 子节点）不再由 dagre 定位，而是按父容器重新
 *      "打包"：task 在 subpipeline 内水平成链、post 子节点在 Post 容器内垂直堆叠，
 *      保证它们一定落在父容器内。
 *   3. 重算各容器（subpipeline / post 父容器 / 根容器）尺寸以包裹子节点，
 *      并把 Post 父容器挂到其源 subpipeline 正下方。
 */
export function applyEditorAutoLayout(
  nodes: Node<EditorNodeData>[],
  edges: Edge<EditorEdgeData>[],
): Node<EditorNodeData>[] {
  const { GAP_X, GAP_Y, NODE_W, NODE_H, CONTAINER_PADDING, HEADER_H, SENTINEL_GAP, SENTINEL_START_W, SENTINEL_H } = EDITOR_LAYOUT;

  const byId = new Map(nodes.map((n) => [n.id, n]));
  if (!byId.has(ROOT)) {
    // 极端兜底：无根容器时不强行分层，退回旧的单层 dagre（避免崩溃）
    return applyDagreLayout(nodes, edges) as unknown as Node<EditorNodeData>[];
  }

  const result = new Map(nodes.map((n) => [n.id, { ...n, position: { ...n.position } }]));

  // === 1) 顶层容器图进 dagre ===
  const dagreNodes = nodes.filter((n) => !n.parentId || n.parentId === ROOT);
  const dagreIds = new Set(dagreNodes.map((n) => n.id));
  const dagreEdges = edges.filter((e) => dagreIds.has(e.source) && dagreIds.has(e.target));
  const layouted = applyDagreLayout(dagreNodes, dagreEdges) as unknown as Node<EditorNodeData>[];
  const layoutMap = new Map(layouted.map((n) => [n.id, n]));
  const rootLayout = layoutMap.get(ROOT);

  for (const n of dagreNodes) {
    const laid = layoutMap.get(n.id);
    if (!laid) continue;
    if (!n.parentId) {
      // start / end / 根容器：绝对坐标
      result.get(n.id)!.position = { ...laid.position };
    } else {
      // 直接挂在根容器下的子容器（subpipeline / post 父容器 / 根级 task）：
      // 转为相对根容器的偏移
      const rx = rootLayout ? laid.position.x - rootLayout.position.x : laid.position.x;
      const ry = rootLayout ? laid.position.y - rootLayout.position.y : laid.position.y;
      result.get(n.id)!.position = { x: rx, y: ry };
    }
  }

  // === 2) 各 subpipeline 内的 task 水平成链，并收紧容器尺寸 ===
  const subs = nodes.filter((n) => n.type === 'editorSubPipeline');
  for (const sub of subs) {
    const tasks = nodes.filter((n) => n.type === 'editorTask' && n.parentId === sub.id);
    const ordered = orderTasks(tasks, edges);
    ordered.forEach((t, i) => {
      result.get(t.id)!.position = {
        x: CONTAINER_PADDING + i * (NODE_W + GAP_X),
        y: HEADER_H + 16,
      };
    });
    const n = ordered.length;
    const w = Math.max(240, CONTAINER_PADDING * 2 + n * NODE_W + Math.max(0, n - 1) * GAP_X);
    const h = HEADER_H + 16 + NODE_H + 24;
    const subNode = result.get(sub.id)!;
    subNode.style = { ...(subNode.style as object), width: w, height: h };
    subNode.width = w;
    subNode.height = h;
  }

  // === 3) Post 父容器挂到其源 subpipeline 正下方 ===
  const postParents = nodes.filter((n) => n.type === 'editorPostParent');
  for (const pp of postParents) {
    const subId = (pp.data as { parentTaskId?: string })?.parentTaskId;
    const sub = subId ? result.get(subId) : undefined;
    if (sub) {
      const subH = (sub.style as { height?: number })?.height ?? HEADER_H + 16 + NODE_H + 24;
      result.get(pp.id)!.position = {
        x: sub.position.x,
        y: sub.position.y + subH + 40,
      };
    }
  }

  // === 4) Post 父容器内 post 子节点垂直堆叠，并收紧容器尺寸 ===
  for (const pp of postParents) {
    const children = nodes.filter((n) => n.type === 'editorPostChild' && n.parentId === pp.id);
    children.forEach((c, i) => {
      result.get(c.id)!.position = {
        x: CONTAINER_PADDING,
        y: CONTAINER_PADDING + i * (NODE_H + GAP_Y),
      };
    });
    const n = children.length;
    const w = 280;
    const h = CONTAINER_PADDING * 2 + n * NODE_H + Math.max(0, n - 1) * GAP_Y;
    const ppNode = result.get(pp.id)!;
    ppNode.style = { ...(ppNode.style as object), width: w, height: h };
    ppNode.width = w;
    ppNode.height = h;
  }

  // === 5) 根容器尺寸包裹所有直接子节点 ===
  const root = result.get(ROOT)!;
  const rootChildren = nodes.filter((n) => n.parentId === ROOT);
  let maxX = 0;
  let maxY = 0;
  for (const c of rootChildren) {
    const rc = result.get(c.id)!;
    const w = (rc.style as { width?: number })?.width ?? (rc.type === 'editorTask' ? NODE_W : 200);
    const h = (rc.style as { height?: number })?.height ?? NODE_H;
    maxX = Math.max(maxX, rc.position.x + (typeof w === 'number' ? w : 0));
    maxY = Math.max(maxY, rc.position.y + (typeof h === 'number' ? h : 0));
  }
  const rw = maxX + CONTAINER_PADDING;
  const rh = maxY + CONTAINER_PADDING;
  root.style = { ...(root.style as object), width: rw, height: rh };
  root.width = rw;
  root.height = rh;

  // === 6) start/end 贴根容器两侧垂直居中（顺流 LR 哨兵位） ===
  const startNode = result.get('__start__');
  const endNode = result.get('__end__');
  if (startNode) {
    startNode.position = { x: -SENTINEL_START_W - SENTINEL_GAP, y: rh / 2 - SENTINEL_H / 2 };
  }
  if (endNode) {
    endNode.position = { x: rw + SENTINEL_GAP, y: rh / 2 - SENTINEL_H / 2 };
  }

  return nodes.map((n) => result.get(n.id)!);
}

/**
 * 按 depends_on 拓扑序排列 subpipeline 内 task，无依赖/成环时回退到原始顺序。
 * 为什么不是直接按索引：依赖顺序才是真实的执行先后，自动布局应尊重它。
 */
function orderTasks(tasks: Node<EditorNodeData>[], edges: Edge<EditorEdgeData>[]): Node<EditorNodeData>[] {
  const ids = tasks.map((t) => t.id);
  const idSet = new Set(ids);
  const indeg = new Map(ids.map((id) => [id, 0]));
  const adj = new Map(ids.map((id) => [id, [] as string[]]));
  for (const e of edges) {
    if (idSet.has(e.source) && idSet.has(e.target) && e.source !== e.target) {
      adj.get(e.source)!.push(e.target);
      indeg.set(e.target, indeg.get(e.target)! + 1);
    }
  }
  const queue = ids.filter((id) => indeg.get(id) === 0);
  const ordered: string[] = [];
  const visited = new Set<string>();
  while (queue.length) {
    const id = queue.shift()!;
    if (visited.has(id)) continue;
    visited.add(id);
    ordered.push(id);
    for (const nb of adj.get(id)!) {
      indeg.set(nb, indeg.get(nb)! - 1);
      if (indeg.get(nb) === 0) queue.push(nb);
    }
  }
  for (const id of ids) if (!visited.has(id)) ordered.push(id);
  const map = new Map(tasks.map((t) => [t.id, t]));
  return ordered.map((id) => map.get(id)!);
}
