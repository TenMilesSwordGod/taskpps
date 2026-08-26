import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import SubpipelineGroupNode from '../SubpipelineGroupNode';

/**
 * v11 (2026-08): LR 流向配套测试（原 v5/v9 TB 契约随视觉世界替换翻转）
 * - 四个 handle 迁移到左右缘中心（top: 50%）—— 入口在左、出口在右，
 *   消除水平流向下的绕行
 * - 朝向与走线一致：top/top-out 朝 Left（外线从左进、内线向右走进组内），
 *   bottom/exit 朝 Right（内线从左汇入、外线向右流向 END）
 * - handle id 契约（top/top-out/bottom/exit）不变 —— usePipelineGraph 依赖
 */
function renderGroup(taskCount = 2) {
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
        data={{ label: 'Sync Automation code', taskCount }}
      />
    </ReactFlowProvider>,
  );
}

describe('SubpipelineGroupNode — handle 合并与任务徽章（n8n 风格修复）', () => {
  it('RED: 四个 handle 均应位于垂直中心（top: 50%），LR 流向左右进出', () => {
    const { container } = renderGroup();
    const handles = container.querySelectorAll('.react-flow__handle');
    expect(handles).toHaveLength(4);
    for (const h of handles) {
      expect((h as HTMLElement).style.top).toBe('50%');
    }
  });

  it('RED: handle 的 id 应保留 top/top-out/bottom/exit（usePipelineGraph 依赖这些 id 路由）', () => {
    const { container } = renderGroup();
    // ReactFlow 写入的 data-id 为复合格式 "{index}-{nodeId}-{handleId}-{type}"（如 1-null-top-target）
    const ids = Array.from(container.querySelectorAll('.react-flow__handle')).map(
      (h) => (h as HTMLElement).dataset.id ?? '',
    );
    expect(ids.some((id) => id.includes('-top-'))).toBe(true);
    expect(ids.some((id) => id.includes('-top-out-'))).toBe(true);
    expect(ids.some((id) => id.includes('-bottom-'))).toBe(true);
    expect(ids.some((id) => id.includes('-exit-'))).toBe(true);
  });

  it('RED: 任务数应渲染为明确的 "N tasks" 徽章（替代含义不明的 "/ N"）', () => {
    const { container } = renderGroup(3);
    expect(container.textContent).toContain('3 tasks');
    expect(container.textContent).not.toContain('/ 3');
  });

  it('RED: 组名与任务数同时可见', () => {
    const { container } = renderGroup(2);
    expect(container.textContent).toContain('Sync Automation code');
    expect(container.textContent).toContain('2 tasks');
  });

  // v11 (2026-08): LR 朝向契约 —— 外部拓扑 handle 与内部走线 handle 均按
  // 水平流向定向（bezier 控制点顺流，弧线不出组）。
  // data-id 复合格式 "{index}-{nodeId}-{handleId}-{type}"，末段区分 target/source。
  it('RED: 入口 handle 朝 Left、出口 handle 朝 Right（连线方向与 LR 走线一致）', () => {
    const { container } = renderGroup();
    const handles = Array.from(
      container.querySelectorAll('.react-flow__handle'),
    ) as HTMLElement[];
    const byHandle = (frag: string) =>
      handles.find((h) => (h.dataset.id ?? '').includes(frag));
    const topOut = byHandle('-top-out-source');
    const exit = byHandle('-exit-target');
    const top = byHandle('-top-target');
    const bottom = byHandle('-bottom-source');
    expect(topOut).toBeDefined();
    expect(exit).toBeDefined();
    // 入口对（top/top-out）朝左：外部线从左进、内部线向右走进组内
    expect(topOut!.className).toContain('react-flow__handle-left');
    expect(top!.className).toContain('react-flow__handle-left');
    // 出口对（bottom/exit）朝右：内部线从左汇入、外部线向右流向 END
    expect(exit!.className).toContain('react-flow__handle-right');
    expect(bottom!.className).toContain('react-flow__handle-right');
  });
});
