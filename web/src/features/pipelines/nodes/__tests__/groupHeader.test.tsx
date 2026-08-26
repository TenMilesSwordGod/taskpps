import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import SubpipelineGroupNode from '../SubpipelineGroupNode';

/**
 * v7 (2026-08): 分组容器实体化 —— 悬浮 pill 标签改为组内 header 行
 * v11 (2026-08): 视觉世界替换 —— header 收敛为 sans 弱文本（名称 · SEQ · N tasks），
 * 容器圆角 14，handle 随 LR 流向迁移到左右缘（top: 50%）
 *
 * 契约：
 *   1. header 行在组内顶部：组名 + 策略码（SEQ/PAR）+ 任务数
 *   2. 容器半透浅底（非透明）+ 圆角 14
 *   3. handle 保持左右中心单点（v11 LR 修复，入口左/出口右）
 */

function renderGroup(data: Record<string, unknown> = {}) {
  return render(
    <ReactFlowProvider>
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
        data={{ label: 'Sync Automation code', taskCount: 2, strategy: 'sequential', ...data }}
      />
    </ReactFlowProvider>,
  );
}

describe('SubpipelineGroupNode — 实体化 header', () => {
  it('RED: 组内 header 行含组名、策略徽章、任务数', () => {
    const { container } = renderGroup();
    const text = container.textContent ?? '';
    expect(text).toContain('Sync Automation code');
    expect(text).toContain('SEQ');
    expect(text).toContain('2 tasks');
  });

  it('RED: parallel 策略显示 PAR 徽章', () => {
    const { container } = renderGroup({ strategy: 'parallel' });
    expect(container.textContent).toContain('PAR');
  });

  it('RED: 容器为半透白实底 + 圆角 14', () => {
    const { container } = renderGroup();
    const root = container.firstElementChild as HTMLElement;
    expect(root.style.background).toContain('rgba');
    expect(root.style.background).not.toBe('transparent');
    expect(root.style.borderRadius).toBe('14px');
  });

  it('RED: handle 仍为左右中心单点（v11 LR 修复不回退）', () => {
    const { container } = renderGroup();
    const handles = container.querySelectorAll('.react-flow__handle');
    expect(handles).toHaveLength(4);
    for (const h of handles) {
      expect((h as HTMLElement).style.top).toBe('50%');
    }
  });
});
