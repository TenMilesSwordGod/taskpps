import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/react';
import WorkflowEditor from '../WorkflowEditor';
import type { PipelineDetail } from '@/types';

/**
 * Bug #37 RED 测试：Post 父容器右键菜单应能添加 on_fail/on_success/always 子容器。
 *
 * 预期行为：右键点击 Post 父容器节点（type=editorPostParent）时，菜单出现
 * "添加 on_fail 子容器 / 添加 on_success 子容器 / 添加 always 子容器" 三项；
 * 点击其中任一项后，应真正向该 Post 父容器内新增对应 type=editorPostChild、
 * postVariant 匹配且 parentId 等于 Post 父容器的节点。
 *
 * 当前（bug）表现：菜单项虽被渲染，但点击后画布并未新增任何 Post 子容器节点。
 * 根因位于 handleAddNodeFromContext —— 它不处理 'post_child_*' 类型
 * （newNode 始终为 null，setNodes/onGraphChange 不被调用），导致点击菜单项无效果。
 * 本测试断言"点击后能新增对应 Post 子容器"，必然在修复前确定性失败（RED）。
 */

// 仅含 on_success 子容器，便于验证点击"添加 on_fail 子容器"能新增 on_fail 子节点
function makePostPipeline(): PipelineDetail {
  return {
    name: 'post-ctx',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [{ name: 't1', command: 'echo 1', env: {}, retry: 0, depends_on: [] }],
        post: {
          on_success: [
            { name: 'notify', command: 'echo done', env: {}, retry: 0, depends_on: [] },
          ],
        },
      },
    ],
  };
}

// 仅收集自定义 fallback 菜单（zIndex 1001，非 antd 0x0 隐式 div）中的菜单项
function findMenuItems(container: HTMLElement, text: string): HTMLElement[] {
  const result: HTMLElement[] = [];
  const fixedContainers = container.querySelectorAll('div[style*="position: fixed"]');
  for (const fixedDiv of fixedContainers) {
    const style = fixedDiv.getAttribute('style') ?? '';
    if (style.includes('width: 0') || style.includes('height: 0')) continue;
    for (const child of fixedDiv.children) {
      if (child instanceof HTMLElement && child.textContent?.trim() === text) {
        result.push(child);
      }
    }
  }
  return result;
}

describe('Bug#37 — Post 父容器右键菜单添加 Post 子容器', () => {
  it('右键 Post 父容器菜单点击"添加 on_fail 子容器"应新增 on_fail 子容器节点', async () => {
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={makePostPipeline()}
        selectedNodeId={null}
        onNodeSelect={() => {}}
        onGraphChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    // 1) 定位 Post 父容器节点
    const postParent = container.querySelector('[data-id^="__post__"]');
    expect(postParent).not.toBeNull();

    // 2) 右键唤起上下文菜单
    fireEvent.contextMenu(postParent!, { clientX: 400, clientY: 300 });

    // 3) 菜单应包含三个 Post 子容器添加项
    await waitFor(() => {
      expect(findMenuItems(container, '添加 on_fail 子容器').length).toBeGreaterThan(0);
      expect(findMenuItems(container, '添加 on_success 子容器').length).toBeGreaterThan(0);
      expect(findMenuItems(container, '添加 always 子容器').length).toBeGreaterThan(0);
    });

    // 当前画布不应已存在 on_fail 子容器（仅构造了 on_success）
    expect(container.querySelector('[data-id*="_on_fail_"]')).toBeNull();

    // 4) 点击"添加 on_fail 子容器"
    const items = findMenuItems(container, '添加 on_fail 子容器');
    fireEvent.click(items[items.length - 1]);

    // 5) 期望：画布新增一个 on_fail 的 Post 子容器节点（且位于该 Post 父容器内部）
    //    修复前此断言失败（点击后无任何节点新增）。
    await waitFor(() => {
      const onFailChild = container.querySelector('[data-id*="__post____pipeline__build_parent_on_fail_"]');
      expect(onFailChild).not.toBeNull();
    });

    unmount();
  });
});
