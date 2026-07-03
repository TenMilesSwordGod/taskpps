import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';

const NODE_WIDTH = 200;
const NODE_HEIGHT = 48;
const GATEWAY_SIZE = 50;

function getNodeSize(node: Node, groupSizes?: Map<string, { width: number; height: number }>) {
  const custom = groupSizes?.get(node.id);
  if (custom) return { width: custom.width, height: custom.height };
  if (node.type === 'whenNode') return { width: GATEWAY_SIZE, height: GATEWAY_SIZE };
  return { width: NODE_WIDTH, height: NODE_HEIGHT };
}

/** 使用 dagre 计算自动布局 */
export function applyDagreLayout<N extends Record<string, unknown>, E extends Record<string, unknown>>(
  nodes: Node<N>[],
  edges: Edge<E>[],
  groupSizes?: Map<string, { width: number; height: number }>,
): Node<N>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 20 });

  for (const node of nodes) {
    const { width, height } = getNodeSize(node, groupSizes);
    g.setNode(node.id, { width, height });
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    const { width, height } = getNodeSize(node, groupSizes);
    return {
      ...node,
      position: {
        x: pos.x - width / 2,
        y: pos.y - height / 2,
      },
    };
  });
}
