import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';

// 以下常量应与 nodeTokens.ts 中的 NODE_SIZE 保持一致
const NODE_WIDTH = 150;
const NODE_HEIGHT = 36;
const DECISION_SIZE = 76;

function getNodeSize(node: Node, groupSizes?: Map<string, { width: number; height: number }>) {
  const custom = groupSizes?.get(node.id);
  if (custom) return { width: custom.width, height: custom.height };
  if (node.type === 'decisionNode') return { width: DECISION_SIZE, height: DECISION_SIZE };
  return { width: NODE_WIDTH, height: NODE_HEIGHT };
}

/** 使用 dagre 计算自动布局 —— 工程蓝图：紧凑、对齐 */
export function applyDagreLayout<N extends Record<string, unknown>, E extends Record<string, unknown>>(
  nodes: Node<N>[],
  edges: Edge<E>[],
  groupSizes?: Map<string, { width: number; height: number }>,
): Node<N>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 70, ranksep: 72 });

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
