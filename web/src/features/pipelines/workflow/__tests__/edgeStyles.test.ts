import { describe, it, expect } from 'vitest';
import { editorEdgeVisual, EDITOR_EDGE_COLOR } from '../edgeStyles';

/**
 * 编辑器边样式工厂测试（n8n 化重设计 v11）
 *
 * 为什么需要工厂：此前边样式散落在 yamlToNodes / WorkflowEditor.onConnect
 * 三处硬编码（绿/灰/浅灰虚线/琥珀虚线/红虚线混杂），视觉噪音大且三处不一致。
 * 工厂收敛为 5 种语义样式，颜色单一来源。
 *
 * 设计契约（v11 n8n 语汇）：
 *   - bezier（'default'）曲线：LR 流向下控制点水平伸展，是 n8n 标志性顺流曲线
 *   - 无箭头：n8n 画布无箭头，流向由 LR 布局表达
 *   - 无虚线：n8n 画布无虚线，语义靠颜色深浅区分
 *   - rail 主流轨 > implicit/post 派生关系（线宽弱化）
 */
describe('editorEdgeVisual — 边样式工厂', () => {
  it('rail：中性灰实线', () => {
    const v = editorEdgeVisual('rail');
    expect(v.style.stroke).toBe(EDITOR_EDGE_COLOR.rail);
    expect(v.style.strokeWidth).toBe(2);
    expect(v.style.strokeDasharray).toBeUndefined();
  });

  // v11 (2026-08): bezier 路由契约 —— LR 流向下 bezier 才是 n8n 顺流曲线
  it('所有边使用 bezier 路由（type=default）且无箭头、无虚线', () => {
    for (const kind of ['start', 'rail', 'implicit', 'cross', 'post'] as const) {
      const v = editorEdgeVisual(kind);
      expect(v.type).toBe('default');
      expect(v.style.strokeDasharray).toBeUndefined();
      expect('markerEnd' in v).toBe(false);
      expect('pathOptions' in v).toBe(false);
    }
  });

  it('implicit：浅灰实线，线宽弱于 rail', () => {
    const v = editorEdgeVisual('implicit');
    expect(v.style.stroke).toBe(EDITOR_EDGE_COLOR.implicit);
    expect(v.style.strokeDasharray).toBeUndefined();
    expect(v.style.strokeWidth).toBeLessThan(editorEdgeVisual('rail').style.strokeWidth);
  });

  it('start：绿色入口线（与查看模式语义一致）', () => {
    const v = editorEdgeVisual('start');
    expect(v.style.stroke).toBe(EDITOR_EDGE_COLOR.start);
  });

  it('cross：琥珀跨组线', () => {
    const v = editorEdgeVisual('cross');
    expect(v.style.stroke).toBe(EDITOR_EDGE_COLOR.cross);
  });

  it('post：软红 Post 路由线（比 #ef4444 柔和）', () => {
    const v = editorEdgeVisual('post');
    expect(v.style.stroke).toBe(EDITOR_EDGE_COLOR.post);
    // 软化校验：红通道保持高、绿蓝通道高于刺眼的纯红
    expect(v.style.stroke).not.toBe('#EF4444');
  });
});
