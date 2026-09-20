import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';

/**
 * 容器感知的分层布局（Phase 1）
 *
 * 为什么不用 dagreLayout.applyDagreLayout：
 *   dagre 只支持平面图，无法理解 React Flow 的 parentId 嵌套容器。
 *   旧实现把容器和子节点一起丢给 dagre，再把绝对坐标硬转成相对坐标，
 *   导致子节点"到处乱飞"（bug#46）；只读渲染则靠"估算尺寸 → 实际尺寸 →
 *   手动下推防重叠"三层补丁维持，交叉/重叠/错位反复出现。
 *
 * 本实现按"自底向上"分层：
 *   1. 先递归布局最深层的子节点（容器尺寸由内容撑开）
 *   2. 再把子容器当作普通节点，用 dagre 布局其父层
 *   3. 边按"最近公共容器"提升：容器之间的边只在容器层参与布局
 * 这样每层都是平面图，dagre 的能力被正确使用，且不再需要后处理补丁。
 */

/** 节点未测量时按类型回退的默认尺寸（与节点组件 minWidth/minHeight 对齐） */
const DEFAULT_SIZES: Record<string, { width: number; height: number }> = {
  editorTask: { width: 180, height: 56 },
  editorPostChild: { width: 180, height: 56 },
  editorStartEnd: { width: 64, height: 28 },
  editorPostParent: { width: 220, height: 100 },
  editorSubPipeline: { width: 220, height: 120 },
  editorPipeline: { width: 400, height: 200 },
};
const FALLBACK_SIZE = { width: 180, height: 56 };

/** 容器内边距：四周留白，子节点不贴边 */
const PADDING = 24;
/** 容器标题栏预留高度：标题绝对定位 top:8 + 行高，避免子节点压住标题 */
const HEADER = 32;
/** dagre 同层间距与层间距 */
const NODESEP = 40;
const RANKSEP = 60;
/** 无连线节点纵向堆叠间距 */
const ISOLATED_GAP = 16;

interface Size {
  width: number;
  height: number;
}

/**
 * 读取节点尺寸：优先 React Flow 实测值，其次显式 style，最后按类型默认值。
 * 容器节点在递归完成后会把计算尺寸写入 computedSizes，优先返回它。
 */
function getNodeSize(
  node: Node,
  isContainer: boolean,
  computedSizes: Map<string, Size>,
): Size {
  const computed = computedSizes.get(node.id);
  if (isContainer && computed) return computed;
  const measured = (node as { measured?: { width?: number; height?: number } }).measured;
  if (measured?.width && measured?.height) {
    return { width: measured.width, height: measured.height };
  }
  const style = node.style as { width?: number | string; height?: number | string } | undefined;
  const styleW = typeof style?.width === 'number' ? style.width : undefined;
  const styleH = typeof style?.height === 'number' ? style.height : undefined;
  if (styleW && styleH) return { width: styleW, height: styleH };
  return DEFAULT_SIZES[node.type ?? ''] ?? FALLBACK_SIZE;
}

/**
 * 把边端点提升到指定容器层的直接子节点。
 *
 * 为什么需要：dagre 只认识当前层的节点。一条连接深层 task 的边，
 * 在容器层应表现为"连接其所属直接子节点"，否则容器层无法感知依赖方向，
 * 导致容器顺序错误（跨容器依赖看起来没有方向）。
 *
 * @returns 端点在该容器层的直接子节点 id；若端点不在该容器子树内返回 null
 */
function liftToLayer(
  nodeId: string,
  containerId: string | null,
  nodeById: Map<string, Node>,
): string | null {
  let current = nodeById.get(nodeId);
  while (current) {
    const parentId =
      current.parentId && nodeById.has(current.parentId) ? current.parentId : null;
    if (parentId === containerId) return current.id;
    if (parentId === null) return null;
    current = nodeById.get(parentId);
  }
  return null;
}

/**
 * 对一组节点做 dagre 布局，返回左上角相对坐标。
 * 调用方保证传入的是平面图（容器已按尺寸当作叶子节点）。
 */
function dagreLayer(
  nodes: Node[],
  pairs: [string, string][],
  sizeOf: (n: Node) => Size,
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: NODESEP, ranksep: RANKSEP });

  for (const n of nodes) {
    const { width, height } = sizeOf(n);
    g.setNode(n.id, { width, height });
  }
  for (const [source, target] of pairs) {
    g.setEdge(source, target);
  }
  dagre.layout(g);

  const raw = new Map<string, { x: number; y: number }>();
  let minX = Infinity;
  let minY = Infinity;
  for (const n of nodes) {
    const pos = g.node(n.id);
    const { width, height } = sizeOf(n);
    // dagre 输出节点中心点，转成左上角
    const x = pos.x - width / 2;
    const y = pos.y - height / 2;
    raw.set(n.id, { x, y });
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
  }
  return raw;
}

/**
 * 容器感知分层布局主入口。
 *
 * @param nodes React Flow 节点（可含 parentId 嵌套）
 * @param edges React Flow 边（端点可在任意深度）
 * @returns 新节点数组：容器 style 尺寸被内容撑开，所有节点 position 为相对父容器坐标
 */
export function layoutGraph<N extends Node>(nodes: N[], edges: Edge[]): N[] {
  if (nodes.length === 0) return [];

  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  // 直接子节点表；parentId 指向不存在的节点时按根层处理，避免孤儿节点丢失
  const childrenOf = new Map<string | null, Node[]>();
  for (const n of nodes) {
    const parentId = n.parentId && nodeById.has(n.parentId) ? n.parentId : null;
    if (!childrenOf.has(parentId)) childrenOf.set(parentId, []);
    childrenOf.get(parentId)!.push(n);
  }

  const positions = new Map<string, { x: number; y: number }>();
  const computedSizes = new Map<string, Size>();
  const isContainer = (id: string) => (childrenOf.get(id)?.length ?? 0) > 0;
  const sizeOf = (n: Node): Size => getNodeSize(n, isContainer(n.id), computedSizes);

  /** 自底向上布局某一容器层；containerId 为 null 表示根层 */
  function layoutLayer(containerId: string | null): void {
    const children = childrenOf.get(containerId) ?? [];
    if (children.length === 0) return;

    // 1. 先递归布局所有子容器，使其 computedSizes 可用于本层 dagre
    for (const child of children) {
      // v2 (2026-07): 折叠容器不递归布局内部（子节点已隐藏），保持折叠尺寸，
      // 避免点击"布局"把折叠容器重新撑开
      if (isContainer(child.id) && child.data?.collapsed !== true) layoutLayer(child.id);
    }

    // 2. 收集本层子图：直接子节点之间的边（深层边提升到本层）
    const childIds = new Set(children.map((c) => c.id));
    const seenPairs = new Set<string>();
    const pairs: [string, string][] = [];
    const connected = new Set<string>();
    for (const e of edges) {
      const source = liftToLayer(e.source, containerId, nodeById);
      const target = liftToLayer(e.target, containerId, nodeById);
      if (!source || !target || source === target) continue;
      if (!childIds.has(source) || !childIds.has(target)) continue;
      const key = `${source}\u0000${target}`;
      if (seenPairs.has(key)) continue;
      seenPairs.add(key);
      pairs.push([source, target]);
      connected.add(source);
      connected.add(target);
    }

    const involved = children.filter((c) => connected.has(c.id));
    const isolated = children.filter((c) => !connected.has(c.id));
    const layerPositions = new Map<string, { x: number; y: number }>();
    // 根层不预留标题栏，容器层为标题让出 HEADER
    const baseY = containerId === null ? 0 : HEADER + PADDING;

    // 3. 有连线的节点交给 dagre；统一平移到 (PADDING, baseY)
    if (involved.length > 0) {
      const raw = dagreLayer(involved, pairs, sizeOf);
      let minX = Infinity;
      let minY = Infinity;
      for (const p of raw.values()) {
        minX = Math.min(minX, p.x);
        minY = Math.min(minY, p.y);
      }
      for (const [id, p] of raw) {
        layerPositions.set(id, { x: p.x - minX + PADDING, y: p.y - minY + baseY });
      }
    }

    // 4. 无连线的孤立节点放在内容下方。
    //    v2 (2026-07): post 容器内保持纵向堆叠（hook 列表的视觉习惯）；
    //    其他容器（并行任务/无依赖任务）改为横向并排 —— 纵向堆叠会让
    //    PAR 执行策略的任务看起来像串行链，语义误导（截图验证）。
    const isPostContainer =
      containerId !== null && nodeById.get(containerId)?.type === 'editorPostParent';
    let stackX = PADDING;
    let stackY = baseY;
    if (involved.length > 0) {
      let maxBottom = -Infinity;
      let minLeft = Infinity;
      for (const n of involved) {
        const p = layerPositions.get(n.id)!;
        const { height } = sizeOf(n);
        maxBottom = Math.max(maxBottom, p.y + height);
        minLeft = Math.min(minLeft, p.x);
      }
      stackY = maxBottom + RANKSEP;
      stackX = minLeft;
    }
    for (const n of isolated) {
      const { width, height } = sizeOf(n);
      layerPositions.set(n.id, { x: stackX, y: stackY });
      if (isPostContainer) {
        stackY += height + ISOLATED_GAP;
      } else {
        stackX += width + NODESEP;
      }
    }

    for (const n of children) {
      positions.set(n.id, layerPositions.get(n.id)!);
    }

    // 5. 本层容器由子节点边界撑开（内容 + PADDING）
    if (containerId !== null) {
      let maxRight = 0;
      let maxBottom = 0;
      for (const n of children) {
        const p = layerPositions.get(n.id)!;
        const { width, height } = sizeOf(n);
        maxRight = Math.max(maxRight, p.x + width);
        maxBottom = Math.max(maxBottom, p.y + height);
      }
      computedSizes.set(containerId, {
        width: maxRight + PADDING,
        height: maxBottom + PADDING,
      });
    }
  }

  layoutLayer(null);

  // 输出新对象，不修改输入；容器尺寸写回 style 供 React Flow 渲染
  return nodes.map((node) => {
    const computed = computedSizes.get(node.id);
    const style = computed
      ? { ...((node.style as object) ?? {}), width: computed.width, height: computed.height }
      : node.style;
    return {
      ...node,
      position: positions.get(node.id) ?? node.position,
      style,
    };
  });
}
