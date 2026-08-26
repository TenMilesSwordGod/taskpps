import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import DecisionNode from '../DecisionNode';
import WhenNode from '../WhenNode';

/**
 * v6 (2026-08): critique P2 — 条件摘要文本溢出菱形。
 *
 * 根因：DecisionNode 的 summary span 无宽度约束（长变量名横穿菱形轮廓、
 * 压住 yes/no 边锚点）；WhenNode 的 span 是 inline 元素，`max-w-[40px] truncate`
 * 类对非替换 inline 元素不生效（Tailwind 在 jsdom 亦无 CSS）。
 *
 * 契约：两个组件的摘要文本必须以 inline-block + maxWidth + overflow hidden 渲染，
 * 保证在任意条件下都被约束在菱形内部。
 */

// React Flow 的 Handle 依赖 store 上下文，单测中 mock 为空组件
vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
}));

describe('条件摘要文本溢出修复', () => {
  it('RED: DecisionNode 摘要 span 应有 maxWidth + overflow hidden + inline-block', () => {
    const { container } = render(<DecisionNode data={{ when: '${env.ENABLE_LINT}' }} />);
    const span = container.querySelector('[data-testid="decision-node"] span');
    expect(span).not.toBeNull();
    const style = (span as HTMLElement).style;
    expect(style.display).toBe('inline-block');
    expect(style.overflow).toBe('hidden');
    expect(parseInt(style.maxWidth, 10)).toBeGreaterThan(0);
    expect(parseInt(style.maxWidth, 10)).toBeLessThanOrEqual(60);
  });

  it('RED: WhenNode 摘要 span 应有 maxWidth + overflow hidden + inline-block', () => {
    const { container } = render(
      <WhenNode
        data={{
          when: '${env.ENABLE_LIST} == "1"',
          sourceTaskName: 'a',
          targetTaskName: 'b',
        }}
      />,
    );
    const span = container.querySelector('[data-testid="when-node-text"]') as HTMLElement;
    expect(span).not.toBeNull();
    // WhenNode 原实现靠 Tailwind class（jsdom 无 CSS 不生效）——改为 inline style 兜底
    expect(span.style.display).toBe('inline-block');
    expect(span.style.overflow).toBe('hidden');
    expect(parseInt(span.style.maxWidth, 10)).toBeGreaterThan(0);
    expect(parseInt(span.style.maxWidth, 10)).toBeLessThanOrEqual(50);
  });
});
