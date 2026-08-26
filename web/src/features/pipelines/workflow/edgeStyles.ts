/**
 * 编辑器连线样式工厂 —— n8n 化重设计 v9 (2026-08)
 *
 * 为什么收敛到单一工厂：旧版边样式散落在 yamlToNodes（5 处硬编码）与
 * WorkflowEditor.onConnect（1 处）共 6 处，颜色/线型/箭头互不一致，
 * 是"连线丑"的直接来源。现在所有编辑器边视觉从这里取，改一处即全局生效。
 *
 * v11 (2026-08) —— LR 流向下的 n8n 语汇：
 *   - bezier（'default'）曲线：LR 流向下控制点水平伸展，是 n8n 标志性顺流
 *     曲线（v10 弃用 bezier 的"下垂 S 弯"根因是垂直流向，方向翻转后消除）
 *   - 无箭头：n8n 画布无箭头，流向由 LR 布局表达
 *   - 无虚线：n8n 画布无虚线，语义靠颜色深浅区分
 *   - rail/implicit 拉开明暗层级：显式依赖实、隐式序浅（视觉权重）
 */
export const EDITOR_EDGE_COLOR = {
  /** 入口哨兵边（START → 根容器）：绿色，与查看模式"入口"图例同语义 */
  start: '#10B981',
  /** 主流轨（显式 depends_on / 哨兵下行 / 用户新连线）：中性灰 */
  rail: '#A8B0BF',
  /** 隐式顺序边（sequential 推导）：浅灰，视觉权重低于 rail */
  implicit: '#C6CCD8',
  /** 跨 SubPipeline 依赖：琥珀 */
  cross: '#F59E0B',
  /** Post 路由（容器 → Post 容器）：软红（red-400，替代刺眼的 #EF4444） */
  post: '#F87171',
} as const;

export type EditorEdgeKind = keyof typeof EDITOR_EDGE_COLOR;

/**
 * v11: bezier 路由类型（'default'）
 */
export const EDITOR_EDGE_TYPE = 'default' as const;

/**
 * 生成指定语义边的 React Flow 样式配置
 *
 * @param kind 边语义类型
 * @returns 直接可展开进 Edge 的 { type, style }
 */
export function editorEdgeVisual(kind: EditorEdgeKind): {
  type: typeof EDITOR_EDGE_TYPE;
  style: { stroke: string; strokeWidth: number };
} {
  const stroke = EDITOR_EDGE_COLOR[kind];
  // 线宽层级：主语义 2px；implicit/post 派生关系 1.75px
  const strokeWidth = kind === 'implicit' || kind === 'post' ? 1.75 : 2;
  return {
    type: EDITOR_EDGE_TYPE,
    style: { stroke, strokeWidth },
  };
}
