import { expect } from 'vitest';
import type { Node, Edge } from '@xyflow/react';

/**
 * 布局结果的通用断言工具（复杂场景测试共用）
 *
 * 为什么提取：真实样例测试与复杂场景测试都需要按同样的尺寸回退策略
 * 计算节点矩形，否则测试和实现口径不一致会制造假阳性/假阴性。
 * 尺寸策略与 layoutGraph.getNodeSize 保持一致：
 *   实测尺寸 > 显式 style > 类型默认值。
 */

export interface NodeRect {
  x: number;
  y: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
}

const DEFAULT_SIZES: Record<string, { width: number; height: number }> = {
  editorTask: { width: 180, height: 56 },
  editorPostChild: { width: 180, height: 56 },
  editorStartEnd: { width: 64, height: 28 },
  editorPostParent: { width: 220, height: 100 },
  editorSubPipeline: { width: 220, height: 120 },
  editorPipeline: { width: 400, height: 200 },
};
const FALLBACK = { width: 180, height: 56 };

/** 与实现一致的尺寸读取 */
export function nodeSizeOf(n: Node): { width: number; height: number } {
  const style = n.style as { width?: number; height?: number } | undefined;
  const measured = (n as { measured?: { width?: number; height?: number } }).measured;
  if (measured?.width && measured?.height) return { width: measured.width, height: measured.height };
  if (typeof style?.width === 'number' && typeof style?.height === 'number') {
    return { width: style.width, height: style.height };
  }
  return DEFAULT_SIZES[n.type ?? ''] ?? FALLBACK;
}

export function nodeRectOf(n: Node): NodeRect {
  const { width, height } = nodeSizeOf(n);
  return {
    x: n.position.x,
    y: n.position.y,
    width,
    height,
    right: n.position.x + width,
    bottom: n.position.y + height,
  };
}

export function rectsOverlap(a: NodeRect, b: NodeRect): boolean {
  return a.x < b.right && b.x < a.right && a.y < b.bottom && b.y < a.bottom;
}

/** 断言：同一父容器下的所有节点两两不重叠 */
export function assertNoSiblingOverlap(nodes: Node[], label: string) {
  const byParent = new Map<string | null, Node[]>();
  for (const n of nodes) {
    const pid = n.parentId ?? null;
    if (!byParent.has(pid)) byParent.set(pid, []);
    byParent.get(pid)!.push(n);
  }
  for (const [parentId, siblings] of byParent) {
    for (let i = 0; i < siblings.length; i++) {
      for (let j = i + 1; j < siblings.length; j++) {
        const a = nodeRectOf(siblings[i]);
        const b = nodeRectOf(siblings[j]);
        expect(
          rectsOverlap(a, b),
          `${label}: 父容器 ${parentId ?? 'root'} 下 ${siblings[i].id} 与 ${siblings[j].id} 重叠`,
        ).toBe(false);
      }
    }
  }
}

/** 断言：每个容器的直接子节点都落在容器尺寸范围内 */
export function assertChildrenInsideContainers(nodes: Node[], label: string) {
  const hasChildren = new Set(nodes.filter((n) => n.parentId).map((n) => n.parentId!));
  for (const container of nodes.filter((n) => hasChildren.has(n.id))) {
    const { width, height } = nodeSizeOf(container);
    for (const child of nodes.filter((n) => n.parentId === container.id)) {
      const c = nodeRectOf(child);
      expect(
        c.x >= 0 && c.y >= 0 && c.right <= width + 0.01 && c.bottom <= height + 0.01,
        `${label}: 容器 ${container.id}(${width}x${height}) 未包裹 ${child.id}(${JSON.stringify(c)})`,
      ).toBe(true);
    }
  }
}

/** 断言：所有节点坐标有限（无 NaN/Infinity） */
export function assertFinitePositions(nodes: Node[], label: string) {
  for (const n of nodes) {
    expect(
      Number.isFinite(n.position.x) && Number.isFinite(n.position.y),
      `${label}: 节点 ${n.id} 坐标非法 (${n.position.x}, ${n.position.y})`,
    ).toBe(true);
  }
}

/** 断言：所有边的端点都能在节点集合中找到（无悬空边） */
export function assertEdgesResolvable(nodes: Node[], edges: Edge[], label: string) {
  const ids = new Set(nodes.map((n) => n.id));
  for (const e of edges) {
    expect(ids.has(e.source), `${label}: 边 ${e.id} 的 source ${e.source} 不存在`).toBe(true);
    expect(ids.has(e.target), `${label}: 边 ${e.id} 的 target ${e.target} 不存在`).toBe(true);
  }
}
