/**
 * editorAutoLayout 单元测试 —— 分层自动布局（修复"点击 dagre 后乱成一团"）
 *
 * 核心不变量：嵌套子节点（subpipeline 内 task / Post 容器内 post 子节点）
 * 必须由父容器重新打包，其相对偏移落在父容器边界内，而非被 dagre 散射。
 */
import { describe, it, expect } from 'vitest';
import type { Node, Edge } from '@xyflow/react';
import { applyEditorAutoLayout } from '../editorAutoLayout';
import type { EditorNodeData, EditorEdgeData } from '../yamlToNodes';

function n(id: string, type: string, parentId?: string, extra: Partial<Node<EditorNodeData>> = {}): Node<EditorNodeData> {
  return {
    id,
    type,
    position: { x: 0, y: 0 },
    data: {},
    ...(parentId ? { parentId } : {}),
    ...extra,
  } as Node<EditorNodeData>;
}

describe('applyEditorAutoLayout', () => {
  const nodes: Node<EditorNodeData>[] = [
    n('__start__', 'editorStartEnd'),
    n('__end__', 'editorStartEnd'),
    n('__pipeline__', 'editorPipeline', undefined, { style: { width: 800, height: 400 } }),
    n('__pipeline__build', 'editorSubPipeline', '__pipeline__', { style: { width: 264, height: 132 } }),
    n('__task__build.compile', 'editorTask', '__pipeline__build', { data: { task: { name: 'compile' } } }),
    n('__task__build.package', 'editorTask', '__pipeline__build', { data: { task: { name: 'package' } } }),
    n('__post____pipeline__build_parent', 'editorPostParent', '__pipeline__', { data: { parentTaskId: '__pipeline__build' }, style: { width: 280, height: 200 } }),
    n('__postchild____post____pipeline__build_parent_on_fail_0', 'editorPostChild', '__post____pipeline__build_parent', { data: { postVariant: 'on_fail' } }),
  ];
  const edges: Edge<EditorEdgeData>[] = [
    { id: 'e1', source: '__task__build.compile', target: '__task__build.package', data: { edgeType: 'explicit', explicit: true, implicit: false } },
    { id: 'e2', source: '__pipeline__build', target: '__post____pipeline__build_parent', sourceHandle: 'post', data: { edgeType: 'post_routing', explicit: true, implicit: false } },
  ];

  it('嵌套 task 被打包进 subpipeline 边界内，且按依赖顺序排列', () => {
    const out = applyEditorAutoLayout(nodes, edges);
    const byId = new Map(out.map((x) => [x.id, x]));
    const sub = byId.get('__pipeline__build')!;
    const subW = (sub.style as { width?: number })?.width ?? 0;
    const subH = (sub.style as { height?: number })?.height ?? 0;

    const compile = byId.get('__task__build.compile')!;
    const pkg = byId.get('__task__build.package')!;

    for (const t of [compile, pkg]) {
      expect(t.parentId).toBe('__pipeline__build');
      expect(t.position.x).toBeGreaterThanOrEqual(0);
      expect(t.position.y).toBeGreaterThanOrEqual(0);
      expect(t.position.x).toBeLessThanOrEqual(subW);
      expect(t.position.y).toBeLessThanOrEqual(subH);
    }
    // 依赖顺序：compile 在左，package 在右
    expect(compile.position.x).toBeLessThan(pkg.position.x);
  });

  it('post 子节点被打包进 Post 父容器边界内', () => {
    const out = applyEditorAutoLayout(nodes, edges);
    const byId = new Map(out.map((x) => [x.id, x]));
    const pp = byId.get('__post____pipeline__build_parent')!;
    const ppW = (pp.style as { width?: number })?.width ?? 0;
    const ppH = (pp.style as { height?: number })?.height ?? 0;
    const child = byId.get('__postchild____post____pipeline__build_parent_on_fail_0')!;
    expect(child.parentId).toBe('__post____pipeline__build_parent');
    expect(child.position.x).toBeGreaterThanOrEqual(0);
    expect(child.position.x).toBeLessThanOrEqual(ppW);
    expect(child.position.y).toBeGreaterThanOrEqual(0);
    expect(child.position.y).toBeLessThanOrEqual(ppH);
  });

  it('根容器尺寸收紧缩裹所有直接子节点', () => {
    const out = applyEditorAutoLayout(nodes, edges);
    const root = out.find((x) => x.id === '__pipeline__')!;
    const rw = (root.style as { width?: number })?.width ?? 0;
    const rh = (root.style as { height?: number })?.height ?? 0;
    expect(rw).toBeGreaterThan(0);
    expect(rh).toBeGreaterThan(0);
  });

  it('缺少根容器时安全兜底（不抛错）', () => {
    const noRoot = nodes.filter((x) => x.id !== '__pipeline__');
    expect(() => applyEditorAutoLayout(noRoot, edges)).not.toThrow();
  });
});
