import { describe, it, expect } from 'vitest';
import { renderWithProvider } from '../test-utils';
import EditorSubPipelineNode from '../../nodes/EditorSubPipelineNode';
import EditorTaskNode from '../../nodes/EditorTaskNode';
import EditorPostParentNode from '../../nodes/EditorPostParentNode';

/**
 * Bug #44 回归测试：容器节点 resize 手柄
 *
 * 期望：容器节点应有 resize 手柄（NodeResizer 渲染 .react-flow__resize-control），
 * 用户可通过拖拽手柄改变节点的宽高。
 */
describe('Bug #44 — 容器节点缺失 resize 手柄', () => {
  it('EditorSubPipelineNode 渲染时应包含 resize 控制元素', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );

    // NodeResizer 会在容器内渲染 .react-flow__resize-control
    // 当前未使用 NodeResizer → 期望 0 个匹配 → 断言失败
    const resizeControls = container.querySelectorAll('.react-flow__resize-control');
    expect(resizeControls.length).toBeGreaterThan(0);

    unmount();
  });

  it('EditorTaskNode 渲染时应包含 resize 控制元素', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode
        data={{
          task: { name: 'compile', command: 'gcc main.c', env: {}, retry: 0, depends_on: [] },
        }}
      />,
    );

    const resizeControls = container.querySelectorAll('.react-flow__resize-control');
    expect(resizeControls.length).toBeGreaterThan(0);

    unmount();
  });

  it('EditorPostParentNode 渲染时应包含 resize 控制元素', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );

    const resizeControls = container.querySelectorAll('.react-flow__resize-control');
    expect(resizeControls.length).toBeGreaterThan(0);

    unmount();
  });
});
