import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import { isContentChange } from '../dirtyGuard';
import type { WorkflowEditorRef } from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * v6 (2026-08): critique P1 — 破坏性操作三连漏洞
 *
 * 1. dimensions/select 变化误置 dirty（React Flow 内部测量与选择态 ≠ 用户改内容）
 * 2. 折叠容器无条件 setIsDirty(false)，抹掉真实未保存态 → beforeunload 守卫失效
 * 3. 删除节点即时执行，无确认无撤销
 *
 * 修复契约：
 *   - isContentChange 纯函数：select/dimensions → false；position/add/remove/replace → true
 *   - 折叠保持 dirty 原值（既不置脏也不清脏）
 *   - deleteNode 先弹确认：取消不动图，确认才删除并置 dirty
 */

function makePipeline(): PipelineDetail {
  return {
    name: 'guard-test',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [
          { name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] },
        ],
      },
    ],
  };
}

describe('isContentChange — 内容性变化判定（纯函数）', () => {
  it('RED: select / dimensions 不算内容变化', () => {
    expect(isContentChange([{ type: 'select' } as never])).toBe(false);
    expect(
      isContentChange([
        { type: 'dimensions', id: 'n1', dimensions: { width: 10, height: 10 } } as never,
      ]),
    ).toBe(false);
    // 混合：仅 select+dimensions 组合仍为 false
    expect(
      isContentChange([{ type: 'select' }, { type: 'dimensions' }] as never[]),
    ).toBe(false);
  });

  it('RED: position / add / remove / replace 算内容变化', () => {
    expect(isContentChange([{ type: 'position' } as never])).toBe(true);
    expect(isContentChange([{ type: 'add' } as never])).toBe(true);
    expect(isContentChange([{ type: 'remove' } as never])).toBe(true);
    expect(isContentChange([{ type: 'replace' } as never])).toBe(true);
  });

  it('RED: 边变化中 select 不算、add/remove 算', () => {
    expect(isContentChange([{ type: 'select' }] as never)).toBe(false);
    expect(isContentChange([{ type: 'add' }] as never)).toBe(true);
    expect(isContentChange([{ type: 'remove' }] as never)).toBe(true);
  });
});

describe('删除节点确认（集成）', () => {
  let refValue: WorkflowEditorRef | null = null;
  const onGraphChange = vi.fn();

  beforeEach(() => {
    refValue = null;
    onGraphChange.mockClear();
  });
  afterEach(() => {
    cleanup();
    document
      .querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap')
      .forEach((el) => el.remove());
  });

  async function renderEditor() {
    const { container } = render(
      <WorkflowEditor
        ref={(r) => {
          refValue = r;
        }}
        pipeline={makePipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={onGraphChange}
      />,
    );
    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });
    return container;
  }

  it('RED: deleteNode 先弹确认；取消则图不变，确认后才删除并回传', async () => {
    const container = await renderEditor();
    const taskId = '__task__build.compile';
    expect(container.querySelector(`[data-id="${taskId}"]`)).not.toBeNull();

    // 触发删除 → 应出现确认弹窗而非直接删除
    refValue!.deleteNode(taskId);
    await waitFor(() =>
      expect(document.querySelector('.ant-modal-confirm-title')).not.toBeNull(),
    );

    // 取消 → 图不变、onGraphChange 未被调用
    fireEvent.click(screen.getByRole('button', { name: /取\s*消/ }));
    await waitFor(() =>
      expect(document.querySelector('.ant-modal-confirm')).toBeNull(),
    );
    expect(onGraphChange).not.toHaveBeenCalled();

    // 再次触发并确认 → 删除生效 + 回传新图
    refValue!.deleteNode(taskId);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /确认删除/ })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('button', { name: /确认删除/ }));
    await waitFor(() => expect(onGraphChange).toHaveBeenCalled());
    const [, newNodes] = onGraphChange.mock.calls.at(-1)!;
    expect((newNodes as Array<{ id: string }>).some((n) => n.id === taskId)).toBe(false);
  });

  it('RED: 哨兵节点删除请求不弹确认、不产生变更', async () => {
    await renderEditor();
    refValue!.deleteNode('__start__');
    // 给潜在的错误删除留出暴露窗口
    await new Promise((r) => setTimeout(r, 50));
    expect(document.querySelector('.ant-modal-confirm')).toBeNull();
    expect(onGraphChange).not.toHaveBeenCalled();
  });

  // v7 (2026-08): 折叠功能已随视觉统一移除（菜单入口删除），
  // "折叠不清 dirty" 的守卫逻辑保留在 handleToggleCollapse 中但无用户触发路径，
  // 原集成用例随之退役。dirty 过滤契约由 isContentChange 单测覆盖。
});

/** 从 React Flow 的 fixed 定位容器中找右键菜单项（沿用 collapse.test 的查找策略） */
function findFixedMenuItem(container: HTMLElement, text: string): HTMLElement | null {
  const fixedContainers = container.querySelectorAll('div[style*="position: fixed"]');
  for (const fixedDiv of fixedContainers) {
    if (
      fixedDiv.getAttribute('style')?.includes('width: 0') ||
      fixedDiv.getAttribute('style')?.includes('height: 0')
    )
      continue;
    for (const child of fixedDiv.children) {
      if (child instanceof HTMLElement && child.textContent?.trim() === text) {
        return child;
      }
    }
  }
  return null;
}
