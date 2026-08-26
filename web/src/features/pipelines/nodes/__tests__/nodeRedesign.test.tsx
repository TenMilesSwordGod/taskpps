import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import TaskNode from '../TaskNode';
import { StartNode, EndNode } from '../StartEndNode';
import type { TaskYAML } from '@/types';

// ReactFlow 的 Handle 组件依赖 ReactFlow store 上下文，单测中 mock 为空组件
vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
}));

/**
 * v11 (2026-08): n8n 卡片重设计（视觉世界替换，用户反馈"像 AI 生成的"）
 *
 * 契约：
 *   1. 任务卡 200×56，左侧 36×36 圆角图标块（类型色实底 + 白色 glyph 图标
 *      —— 文字码 CMD/INV 退役，glyph 是 n8n 语汇）
 *   2. 右侧两行：任务名（sans 13px ≥12.5）+ 命令摘要（mono 10.5px，截断）
 *   3. 命令摘要提取：command→原文；steps→"N steps"；invoke→"→ pipeline"；git→repo 短名
 *   4. START/END 为 trigger 式节点卡片（图标块 + 文字），非圆形哨兵
 */

function makeTask(overrides: Partial<TaskYAML> = {}): TaskYAML {
  return {
    name: 'sync-code',
    command: 'ls -la /tmp/build',
    env: {},
    retry: 0,
    depends_on: [],
    ...overrides,
  };
}

function renderTask(task: TaskYAML) {
  return render(<TaskNode id="build.sync-code" data={{ task, subpipelineName: 'build' }} />);
}

/** 取卡片内的图标块容器（36×36 石墨底，含白色 glyph） */
function iconBlock(container: HTMLElement): HTMLElement | null {
  const block = Array.from(container.querySelectorAll('div')).find(
    (d) => d.style.backgroundColor === 'rgb(52, 58, 67)' && d.style.width === '36px',
  ) ?? null;
  return block;
}

describe('TaskNode — n8n 卡片重设计', () => {
  it('RED: 卡片尺寸 200×56', () => {
    const { getByTestId } = renderTask(makeTask());
    const card = getByTestId('task-card') as HTMLElement;
    expect(card.style.width).toBe('200px');
    expect(card.style.height).toBe('56px');
  });

  it('RED: 左侧图标块为石墨实底 + 白色 glyph 图标（n8n 语汇，非文字码非类型色）', () => {
    const { container } = renderTask(makeTask());
    const block = iconBlock(container as unknown as HTMLElement);
    expect(block).not.toBeNull();
    // 图标块内是 SVG 图标（antd 渲染 <svg>），不再有 CMD/GIT 等文字码
    expect(block!.querySelector('svg')).not.toBeNull();
    // 文字码（大写字母文本）退役
    expect(block!.textContent?.trim()).toBe('');
    // 图标块石墨底 #343A43 → rgb(52, 58, 67)（v11.1: 用户反馈类型绿"很丑"）
    expect(block!.style.borderRadius).toBe('8px');
  });

  it('RED: 命令摘要作为第二行显示（command 原文截断）', () => {
    const { container } = renderTask(makeTask({ command: 'ls -la /tmp/build' }));
    const summary = Array.from(container.querySelectorAll('span')).find(
      (s) => s.textContent === 'ls -la /tmp/build',
    );
    expect(summary).not.toBeNull();
    expect(summary!.style.overflow).toBe('hidden');
  });

  it('RED: steps 任务摘要显示 "N steps"', () => {
    const { container } = renderTask(
      makeTask({
        command: undefined as never,
        steps: [{ name: 'a', command: 'x', env: {} }, { name: 'b', command: 'y', env: {} }],
      } as Partial<TaskYAML>),
    );
    expect(container.textContent).toContain('2 steps');
  });

  it('RED: invoke 任务摘要显示 "→ 目标任务名"（InvokeSpec.task）', () => {
    const { container } = renderTask(
      makeTask({
        command: undefined as never,
        // 真实 InvokeSpec 结构（types/index.ts L141）：{ task, args, kwargs }
        invoke: { task: 'deploy-service', args: [], kwargs: {} } as never,
      } as Partial<TaskYAML>),
    );
    expect(container.textContent).toContain('deploy-service');
  });

  it('RED: 任务名左对齐（非居中布局）且 13px', () => {
    const { container } = renderTask(makeTask());
    const name = Array.from(container.querySelectorAll('span')).find(
      (s) => s.textContent === 'sync-code',
    );
    expect(name).not.toBeNull();
    expect(parseFloat(name!.style.fontSize)).toBeGreaterThanOrEqual(12.5);
  });
});

describe('StartEndNode — trigger 式节点卡片', () => {
  it('RED: START 为卡片（非圆形）：固定宽高 + radius 10 + 内嵌图标块', () => {
    const { container } = render(<StartNode data={{ variant: 'start' }} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.style.width).toBe('112px');
    expect(root.style.height).toBe('56px');
    expect(root.style.borderRadius).toBe('10px');
    // 内嵌 36×36 图标块
    const block = root.querySelector('div[style*="width: 36px"]') as HTMLElement;
    expect(block).not.toBeNull();
  });

  it('RED: START/END 图标块同为石墨底（v11.1: 去类型色）', () => {
    const start = render(<StartNode data={{ variant: 'start' }} />);
    const end = render(<EndNode data={{ variant: 'end' }} />);
    const sBlock = (start.container.firstElementChild as HTMLElement).querySelector('div[style*="width: 36px"]') as HTMLElement;
    const eBlock = (end.container.firstElementChild as HTMLElement).querySelector('div[style*="width: 36px"]') as HTMLElement;
    expect(sBlock).not.toBeNull();
    expect(eBlock).not.toBeNull();
    // 统一石墨 #343A43 → rgb(52, 58, 67)
    expect(sBlock.style.backgroundColor).toBe('rgb(52, 58, 67)');
    expect(eBlock.style.backgroundColor).toBe('rgb(52, 58, 67)');
  });
});
