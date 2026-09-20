import { describe, it, expect } from 'vitest';
import type { Node } from '@xyflow/react';
import { applyCollapse, isCollapsed, COLLAPSED_SIZE } from '../collapse';

/**
 * 折叠/展开工具测试
 *
 * 覆盖压测暴露的两个问题：
 *   1. 折叠后子节点仍渲染并溢出紧凑容器 → 折叠时应隐藏全部后代
 *   2. 展开无法恢复原尺寸 → 折叠前保存 style，展开时恢复
 * 以及布局配合：collapsed 容器的尺寸标记供 layoutGraph 跳过递归。
 */

function makeNode(id: string, parentId?: string, data: Record<string, unknown> = {}): Node {
  return {
    id,
    type: 'editorSubPipeline',
    parentId,
    position: { x: 1, y: 2 },
    data,
    style: { width: 260, height: 140, background: 'red' },
  };
}

describe('applyCollapse', () => {
  it('折叠：容器变为紧凑尺寸、标记 collapsed、保留其它样式字段', () => {
    const nodes = [makeNode('sub')];
    const out = applyCollapse(nodes, 'sub', true);
    const sub = out[0];
    expect(sub.data?.collapsed).toBe(true);
    expect(sub.style).toMatchObject({
      width: COLLAPSED_SIZE.width,
      height: COLLAPSED_SIZE.height,
      background: 'red',
    });
    expect(isCollapsed(sub)).toBe(true);
  });

  it('折叠：所有后代（含嵌套）hidden=true，非后代不受影响', () => {
    const nodes = [
      makeNode('sub'),
      makeNode('task-a', 'sub'),
      makeNode('atomic', 'task-a'),
      makeNode('other'),
    ];
    const out = applyCollapse(nodes, 'sub', true);
    expect(out.find(n => n.id === 'task-a')?.hidden).toBe(true);
    expect(out.find(n => n.id === 'atomic')?.hidden).toBe(true);
    expect(out.find(n => n.id === 'other')?.hidden).toBeUndefined();
    // 容器自己不被 hidden（仍要显示折叠框）
    expect(out.find(n => n.id === 'sub')?.hidden).toBeUndefined();
  });

  it('展开：恢复折叠前 style，后代取消 hidden，清理 __expandedStyle', () => {
    const nodes = [makeNode('sub'), makeNode('task-a', 'sub')];
    const collapsed = applyCollapse(nodes, 'sub', true);
    const expanded = applyCollapse(collapsed, 'sub', false);

    const sub = expanded.find(n => n.id === 'sub')!;
    expect(sub.data?.collapsed).toBe(false);
    expect(sub.data?.__expandedStyle).toBeUndefined();
    expect(sub.style).toMatchObject({ width: 260, height: 140, background: 'red' });
    expect(expanded.find(n => n.id === 'task-a')?.hidden).toBe(false);
  });

  it('不修改输入数组（不可变更新）', () => {
    const nodes = [makeNode('sub'), makeNode('task-a', 'sub')];
    const snapshot = JSON.stringify(nodes);
    applyCollapse(nodes, 'sub', true);
    expect(JSON.stringify(nodes)).toBe(snapshot);
  });

  it('isCollapsed：无标记视为未折叠', () => {
    expect(isCollapsed(undefined)).toBe(false);
    expect(isCollapsed(makeNode('x'))).toBe(false);
    expect(isCollapsed(makeNode('x', undefined, { collapsed: true }))).toBe(true);
  });
});
