import { describe, it, expect } from 'vitest';
import { validateDrop } from '../validateDrop';

/**
 * Bug #50: Post 容器无法拖入原子行为
 *
 * 根因：R4 规则将 task_atomic_* 类型误判为容器并拒绝拖入 post_parent
 * 修复：放行 task_atomic_*（非容器），handleDrop 中自动创建 editorPostChild 节点
 */
describe('Bug #50: Post 容器可拖入原子行为', () => {
  it('task_atomic_cmd 拖入 post_parent 应通过验证', () => {
    expect(validateDrop('task_atomic_cmd', 'post_parent', [])).toBeNull();
  });

  it('task_atomic_step 拖入 post_parent 应通过验证', () => {
    expect(validateDrop('task_atomic_step', 'post_parent', [])).toBeNull();
  });

  it('task_atomic_plugin 拖入 post_parent 应通过验证', () => {
    expect(validateDrop('task_atomic_plugin', 'post_parent', [])).toBeNull();
  });

  it('task_atomic_invoke 拖入 post_parent 应通过验证', () => {
    expect(validateDrop('task_atomic_invoke', 'post_parent', [])).toBeNull();
  });

  // 确保 R4 仍然拒绝真正的容器类型
  it('subpipeline 拖入 post_parent 仍应拒绝', () => {
    const result = validateDrop('subpipeline', 'post_parent', []);
    expect(result).toContain('不可嵌套其它容器节点');
  });

  it('task 拖入 post_parent 仍应拒绝', () => {
    const result = validateDrop('task', 'post_parent', []);
    expect(result).toContain('不可嵌套其它容器节点');
  });

  it('post_parent 拖入 post_parent 仍应拒绝（R2 先于 R4 拦截）', () => {
    const result = validateDrop('post_parent', 'post_parent', []);
    expect(result).not.toBeNull();
  });

  // post_child 仍然允许
  it('post_child 拖入 post_parent 仍应通过', () => {
    expect(validateDrop('post_child_on_fail', 'post_parent', [])).toBeNull();
    expect(validateDrop('post_child_on_success', 'post_parent', [])).toBeNull();
    expect(validateDrop('post_child_always', 'post_parent', [])).toBeNull();
  });
});
