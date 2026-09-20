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
  // 展开状态验证：容器应使用弹性 width（修复后确认不再硬编码）
  // v2 (2026-07-21): 修复 width:180 硬编码问题，改为 width:100%
  // ──────────────────────────────────────────────
  it('EditorTaskNode 展开态使用弹性 width（无硬编码 180px）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode
        data={{
          task: { name: 'compile', command: 'gcc main.c', env: {}, retry: 0, depends_on: [] },
        }}
      />,
    );

    const styleAttr = container.firstElementChild?.getAttribute('style') || '';
    expect(styleAttr).not.toMatch(/width:\s*180/);

    unmount();
  });

  it('EditorSubPipelineNode 展开态使用弹性 width: 100%', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );

    const styleAttr = container.firstElementChild?.getAttribute('style') || '';
    expect(styleAttr).toMatch(/width:\s*100%/);

    unmount();
  });

  it('EditorPostParentNode 展开态使用弹性 width: 100%', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );

    const styleAttr = container.firstElementChild?.getAttribute('style') || '';
    expect(styleAttr).toMatch(/width:\s*100%/);

    unmount();
  });

  // ──────────────────────────────────────────────
  // v2 (2026-07-21): 选中 + 非只读模式下手柄应始终可见
  // ──────────────────────────────────────────────
  it('EditorTaskNode selected=true 时包含 resize 手柄', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode
        selected
        data={{
          task: { name: 'compile', command: 'gcc main.c', env: {}, retry: 0, depends_on: [] },
        }}
      />,
    );

    const resizeControls = container.querySelectorAll('.react-flow__resize-control');
    expect(resizeControls.length).toBeGreaterThan(0);

    unmount();
  });
});
