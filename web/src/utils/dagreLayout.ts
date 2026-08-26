import dagre from 'dagre';
import type { Node, Edge } from '@xyflow/react';
import { NODE_SIZE } from '@/features/pipelines/nodes/nodeTokens';

// 以下常量应与 nodeTokens.ts 中的 NODE_SIZE 保持一致
// v7 (2026-08): 统一引用 NODE_SIZE（任务卡 180×52），消除双处硬编码漂移风险
const NODE_WIDTH = NODE_SIZE.TASK_W;
const NODE_HEIGHT = NODE_SIZE.TASK_H;
const DECISION_SIZE = 76;

function getNodeSize(node: Node, groupSizes?: Map<string, { width: number; height: number }>) {
  const custom = groupSizes?.get(node.id);
  if (custom) return { width: custom.width, height: custom.height };
  if (node.type === 'decisionNode') return { width: DECISION_SIZE, height: DECISION_SIZE };
  return { width: NODE_WIDTH, height: NODE_HEIGHT };
}

/**
 * 使用 dagre 计算自动布局
 * v11 (2026-08): n8n 化重设计 —— rankdir TB → LR（水平左→右流动是 n8n 画布的
 * 身份本体；bezier 连线在水平流向下才是"顺流"曲线，垂直流向下会画下垂 S 弯，
 * 这正是 v10 弃用 bezier 的根因，方向翻转后根因消除）。
 * ranksep 80：水平相邻 rank 间给贝塞尔曲线足够的呼吸空间；
 * nodesep 40：同 rank（同列）节点垂直间距。
 */
export function applyDagreLayout<N extends Record<string, unknown>, E extends Record<string, unknown>>(
  nodes: Node<N>[],
  edges: Edge<E>[],
  groupSizes?: Map<string, { width: number; height: number }>,
): Node<N>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 80 });

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
