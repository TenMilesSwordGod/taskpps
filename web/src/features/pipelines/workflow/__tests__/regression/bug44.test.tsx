import { describe, it, expect } from 'vitest';
import { renderWithProvider } from '../test-utils';
import EditorSubPipelineNode from '../../nodes/EditorSubPipelineNode';
import EditorTaskNode from '../../nodes/EditorTaskNode';
import EditorPostParentNode from '../../nodes/EditorPostParentNode';

/**
 * Bug #44 回归测试：容器节点应可自由拖拽调整大小
 *
 * 期望：
 *   1. 容器节点应有 resize 手柄（NodeResizer 渲染 .react-flow__resize-control）
 *   2. 容器展开状态的 width 应为弹性（非硬编码固定值），使 NodeResizer 的尺寸变更可见
 */
describe('Bug #44 — 容器节点缺失 resize 手柄', () => {
  it('EditorSubPipelineNode 渲染时应包含 resize 控制元素', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );

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

  // ──────────────────────────────────────────────
  // RED 测试：展开状态的容器应使用弹性 width（非硬编码固定值）
  // 当前 EditorTaskNode 展开态 div 写死 width: 180，NodeResizer 无法生效
  // ──────────────────────────────────────────────
  it('RED: EditorTaskNode 展开态不应有硬编码的固定 width', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode
        data={{
          task: { name: 'compile', command: 'gcc main.c', env: {}, retry: 0, depends_on: [] },
        }}
      />,
    );

    // container.firstElementChild 是渲染的根 div
    // 当前它包含 "width: 180" → 断言没匹配到 → RED
    const styleAttr = container.firstElementChild?.getAttribute('style') || '';
    expect(styleAttr).not.toMatch(/width:\s*180/);

    unmount();
  });

  it('RED: EditorSubPipelineNode 展开态应使用弹性 width', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );

    // SubPipeline 展开态应使用 "width: 100%" 而非硬编码数值
    const styleAttr = container.firstElementChild?.getAttribute('style') || '';
    expect(styleAttr).toMatch(/width:\s*100%/);

    unmount();
  });

  it('RED: EditorPostParentNode 展开态应使用弹性 width', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );

    const styleAttr = container.firstElementChild?.getAttribute('style') || '';
    expect(styleAttr).toMatch(/width:\s*100%/);

    unmount();
  });
});
