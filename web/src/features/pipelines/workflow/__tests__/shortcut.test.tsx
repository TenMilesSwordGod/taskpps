import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * v6 (2026-08): critique P2 — 工具栏承诺「保存 (Ctrl+S)」但画布 onKeyDown 只实现了
 * Delete/Backspace，快捷键信任落空。契约：容器聚焦时 Cmd/Ctrl+S 触发 onSave 回调。
 */

function makePipeline(): PipelineDetail {
  return {
    name: 'shortcut-test',
    pipelines: [
      { name: 'build', depends_on: [], tasks: [{ name: 't1', command: 'echo', env: {}, retry: 0, depends_on: [] }] },
    ],
  };
}

describe('WorkflowEditor — Ctrl+S 保存快捷键', () => {
  it('RED: 容器内 Cmd/Ctrl+S 触发 onSave', async () => {
    const onSave = vi.fn();
    const { container } = render(
      <WorkflowEditor
        pipeline={makePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onSave={onSave}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const focusable = container.querySelector<HTMLElement>('[tabindex="0"]')!;
    expect(focusable).not.toBeNull();

    // Ctrl+S（Windows/Linux）
    fireEvent.keyDown(focusable, { key: 's', ctrlKey: true });
    expect(onSave).toHaveBeenCalledTimes(1);

    // Cmd+S（macOS）
    fireEvent.keyDown(focusable, { key: 's', metaKey: true });
    expect(onSave).toHaveBeenCalledTimes(2);
  });

  it('RED: 未传 onSave 时不绑定行为也不报错', async () => {
    const { container } = render(
      <WorkflowEditor
        pipeline={makePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );
    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });
    const focusable = container.querySelector<HTMLElement>('[tabindex="0"]')!;
    expect(() =>
      fireEvent.keyDown(focusable, { key: 's', ctrlKey: true }),
    ).not.toThrow();
  });
});
