import { describe, it, expect } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import EdgeLegend from '../EdgeLegend';

/**
 * v6 (2026-08): critique P2 — 四种边线型（绿实线=入口/yes、琥珀虚线=跨组依赖、
 * 灰虚线=条件跳过 alt/no、灰实线=主流程）零解释，全靠记忆（违背「识别优先于回忆」）。
 *
 * 契约：可折叠图例组件 —— 默认展开显示四种线型语义，可通过按钮折叠收起。
 */

describe('EdgeLegend — 边线型图例', () => {
  it('RED: 默认渲染四种边语义说明', () => {
    const { getByTestId } = render(<EdgeLegend />);
    const legend = getByTestId('edge-legend');
    expect(legend.textContent).toContain('入口 / 条件成立');
    expect(legend.textContent).toContain('条件跳过');
    expect(legend.textContent).toContain('跨组依赖');
    expect(legend.textContent).toContain('主流程');
  });

  it('RED: 点击折叠按钮后内容隐藏、再次点击恢复', () => {
    const { getByTestId } = render(<EdgeLegend />);
    const toggle = getByTestId('edge-legend-toggle');

    fireEvent.click(toggle);
    expect(getByTestId('edge-legend').getAttribute('data-collapsed')).toBe('true');

    fireEvent.click(toggle);
    expect(getByTestId('edge-legend').getAttribute('data-collapsed')).toBe('false');
  });
});
