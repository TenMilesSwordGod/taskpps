import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 48;

/** 使用 dagre 计算自动布局 */
export function applyDagreLayout<N extends Record<string, unknown>, E extends Record<string, unknown>>(
  nodes: Node<N>[],
  edges: Edge<E>[],
  groupSizes?: Map<string, { width: number; height: number }>,
): Node<N>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 40, ranksep: 40 });

  for (const node of nodes) {
    const custom = groupSizes?.get(node.id);
    const w = custom?.width ?? NODE_WIDTH;
    const h = custom?.height ?? NODE_HEIGHT;
    g.setNode(node.id, { width: w, height: h });
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    const custom = groupSizes?.get(node.id);
    const w = custom?.width ?? NODE_WIDTH;
    const h = custom?.height ?? NODE_HEIGHT;
    return {
      ...node,
      position: {
        x: pos.x - w / 2,
        y: pos.y - h / 2,
      },
    };
  });
}
