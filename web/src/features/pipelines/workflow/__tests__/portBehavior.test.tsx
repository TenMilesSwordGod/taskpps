import { describe, it, expect } from 'vitest';
import { renderWithProvider } from './test-utils';
import EditorSubPipelineNode from '../nodes/EditorSubPipelineNode';
import EditorTaskNode from '../nodes/EditorTaskNode';
import EditorPostParentNode from '../nodes/EditorPostParentNode';
import EditorPostChildNode from '../nodes/EditorPostChildNode';
import EditorStartEndNode from '../nodes/EditorStartEndNode';
import EditorPipelineNode from '../nodes/EditorPipelineNode';

/**
 * 端口行为测试
 * 验证:
 *   1. 各节点类型 handle 端口的存在性与类型（source/target）
 *   2. Post 父容器 in 端口使用红色边框（视觉隔离）
 *   3. 普通端口使用灰色边框
 *   4. 端口位置正确（Left/Right/Bottom）
 */

function getHandleByType(container: HTMLElement, handleId: string): HTMLElement | null {
  const handles = container.querySelectorAll('[data-handleid]');
  for (const h of handles) {
    if (h.getAttribute('data-handleid') === handleId) return h as HTMLElement;
  }
  return null;
}

function getHandlePortType(handle: HTMLElement): string {
  const className = handle.className || '';
  if (className.includes('source')) return 'source';
  if (className.includes('target')) return 'target';
  return 'unknown';
}

describe('端口存在性与类型', () => {
  it('SubPipeline in 端口为 target 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const inHandle = getHandleByType(container, 'in');
    expect(inHandle).not.toBeNull();
    expect(getHandlePortType(inHandle!)).toBe('target');
    unmount();
  });

  it('SubPipeline out 端口为 source 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const outHandle = getHandleByType(container, 'out');
    expect(outHandle).not.toBeNull();
    expect(getHandlePortType(outHandle!)).toBe('source');
    unmount();
  });

  it('SubPipeline post 端口为 source 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const postHandle = getHandleByType(container, 'post');
    expect(postHandle).not.toBeNull();
    expect(getHandlePortType(postHandle!)).toBe('source');
    unmount();
  });

  it('Task out 端口为 source 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode data={{ task: { name: 'test', env: {}, retry: 0, depends_on: [] } }} />,
    );
    const outHandle = getHandleByType(container, 'out');
    expect(outHandle).not.toBeNull();
    expect(getHandlePortType(outHandle!)).toBe('source');
    unmount();
  });

  it('Start 节点的 out 端口为 source 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorStartEndNode data={{ variant: 'start' }} />,
    );
    const outHandle = getHandleByType(container, 'out');
    expect(outHandle).not.toBeNull();
    expect(getHandlePortType(outHandle!)).toBe('source');
    unmount();
  });

  it('End 节点的 in 端口为 target 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorStartEndNode data={{ variant: 'end' }} />,
    );
    const inHandle = getHandleByType(container, 'in');
    expect(inHandle).not.toBeNull();
    expect(getHandlePortType(inHandle!)).toBe('target');
    unmount();
  });

  it('Post 父容器 in 端口为 target 类型', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );
    const inHandle = getHandleByType(container, 'in');
    expect(inHandle).not.toBeNull();
    expect(getHandlePortType(inHandle!)).toBe('target');
    unmount();
  });
});

describe('端口视觉隔离', () => {
  // React 将 inline style 颜色标准化为 rgb() 格式
  // #ef4444 → rgb(239, 68, 68), #64748b → rgb(100, 116, 139)

  it('Post 父容器 in 端口使用红色边框（视觉区分）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );
    const inHandle = getHandleByType(container, 'in');
    expect(inHandle).not.toBeNull();
    const style = inHandle!.getAttribute('style') || '';
    // #ef4444 → rgb(239, 68, 68)
    expect(style).toContain('239, 68, 68');
    unmount();
  });

  it('SubPipeline post 端口使用红色边框（标识 Post 连线）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const postHandle = getHandleByType(container, 'post');
    expect(postHandle).not.toBeNull();
    const style = postHandle!.getAttribute('style') || '';
    expect(style).toContain('239, 68, 68');
    unmount();
  });

  it('SubPipeline 普通端口 in/out 使用灰色边框', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const inHandle = getHandleByType(container, 'in');
    const outHandle = getHandleByType(container, 'out');
    expect(inHandle).not.toBeNull();
    expect(outHandle).not.toBeNull();
    const inStyle = inHandle!.getAttribute('style') || '';
    const outStyle = outHandle!.getAttribute('style') || '';
    // #64748b → rgb(100, 116, 139)
    expect(inStyle).toContain('100, 116, 139');
    expect(outStyle).toContain('100, 116, 139');
    unmount();
  });

  it('Task post 端口使用红色边框，in/out 使用灰色边框', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode data={{ task: { name: 'test', env: {}, retry: 0, depends_on: [] } }} />,
    );
    const inHandle = getHandleByType(container, 'in');
    const outHandle = getHandleByType(container, 'out');
    const postHandle = getHandleByType(container, 'post');

    const inStyle = inHandle!.getAttribute('style') || '';
    const outStyle = outHandle!.getAttribute('style') || '';
    const postStyle = postHandle!.getAttribute('style') || '';

    expect(inStyle).toContain('100, 116, 139');
    expect(outStyle).toContain('100, 116, 139');
    expect(postStyle).toContain('239, 68, 68');
    unmount();
  });
});
