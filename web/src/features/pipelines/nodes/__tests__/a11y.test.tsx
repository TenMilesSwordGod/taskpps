import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { STATUS_COLOR, TYPE_ICON_BG } from '../nodeTokens';

// ReactFlow 的 Handle 组件依赖 ReactFlow store 上下文，单测中 mock 为空组件
vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
}));
import TaskNode from '../TaskNode';
import SubpipelineGroupNode from '../SubpipelineGroupNode';

/**
 * v11 (2026-08): 无障碍契约（随视觉世界替换更新）
 *
 * 1. pending 与 cancelled 状态色不同 + cancelled 双通道（虚线边框 + 角标），
 *    色弱可辨（延续 v6 结论，载体从"左缘色条"迁移到"边框 + 角标"）
 * 2. 任务名（正文）白底对比 ≥4.5:1；类型图标块白色 glyph 对比 ≥3:1（图标阈值）
 * 3. 状态角标带 role="img" + aria-label（屏幕阅读器可读）
 * 4. 分组任务数弱文本白底对比 ≥4.5:1
 */

/** WCAG 相对亮度对比度计算（支持 #hex 与 rgb() 两种格式） */
function contrastRatio(fg: string, bg: string): number {
  const toRgb = (input: string): [number, number, number] => {
    const m = input.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
    if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
    const c = input.replace('#', '');
    return [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16)) as [number, number, number];
  };
  const lum = (rgb: [number, number, number]) => {
    const [r, g, b] = rgb.map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const l1 = lum(toRgb(fg));
  const l2 = lum(toRgb(bg));
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

describe('状态色可区分性', () => {
  it('RED: cancelled 与 pending 的状态色必须不同', () => {
    expect(STATUS_COLOR.cancelled).not.toBe(STATUS_COLOR.pending);
  });
});

describe('TaskNode — 无障碍渲染', () => {
  function renderTask(status?: string) {
    return render(
      <TaskNode
        id="build.t1"
        data={{
          task: {
            name: 't1',
            command: 'echo hi',
            env: {},
            retry: 0,
            depends_on: [],
          },
          subpipelineName: 'build',
          ...(status ? { status } : {}),
        }}
      />,
    );
  }

  it('RED: 类型图标块白色 glyph 对比度 ≥3:1（UI 图标阈值）', () => {
    const { container } = renderTask();
    // 取图标块（石墨 TYPE_ICON_BG 底）
    const block = Array.from(container.querySelectorAll('div')).find(
      (d) => d.style.backgroundColor === 'rgb(52, 58, 67)',
    );
    expect(block).not.toBeNull();
    expect(contrastRatio('#FFFFFF', TYPE_ICON_BG)).toBeGreaterThanOrEqual(3);
  });

  it('RED: cancelled 状态双通道 —— 虚线边框（颜色之外的第二辨识通道）', () => {
    const { getByTestId } = renderTask('cancelled');
    const card = getByTestId('task-card') as HTMLElement;
    // 双通道：边框色为 cancelled 色（style 归一化为 rgb）+ 虚线线型
    expect(card.style.borderStyle).toBe('dashed');
    expect(card.style.borderColor).toBe('rgb(100, 116, 139)');
  });

  it('pending 状态使用默认实线边框（与 cancelled 不同线型）', () => {
    const { getByTestId } = renderTask('pending');
    const card = getByTestId('task-card') as HTMLElement;
    // pending 是默认态：无状态角标、实线边框（零噪音）
    expect(card.style.borderStyle).toBe('solid');
  });

  it('RED: 非 pending 状态渲染带 aria-label 的角标（屏幕阅读器可读）', () => {
    const { container } = renderTask('success');
    const badge = container.querySelector('[role="img"][aria-label="成功"]');
    expect(badge).not.toBeNull();
  });
});

describe('SubpipelineGroupNode — 任务数弱文本可读性', () => {
  function renderGroup() {
    return render(
      <>
        <SubpipelineGroupNode
          id="__group__build"
          type="subpipelineGroup"
          selected={false}
          draggable={false}
          selectable={false}
          connectable={false}
          deletable={false}
          dragHandle={null}
          zIndex={0}
          positionAbsoluteX={0}
          positionAbsoluteY={0}
          data={{ label: 'Sync code', taskCount: 2 }}
        />
      </>,
    );
  }

  it('RED: 任务数弱文本字号 ≥10px 且文字对比度达到 AA（白底 4.5:1）', () => {
    const { container } = renderGroup();
    const spans = Array.from(container.querySelectorAll('span'));
    const badge = spans.find((s) => /tasks$/.test(s.textContent ?? ''));
    expect(badge).not.toBeNull();
    expect(parseFloat(badge!.style.fontSize)).toBeGreaterThanOrEqual(10);
    expect(contrastRatio(badge!.style.color, '#FFFFFF')).toBeGreaterThanOrEqual(4.5);
  });
});
