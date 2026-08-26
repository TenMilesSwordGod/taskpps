import { describe, it, expect } from 'vitest'
import { applyDagreLayout } from './dagreLayout'
import type { Node, Edge } from '@xyflow/react'

// v11 (2026-08): n8n 化重设计 —— 画布流向从垂直 TB 翻转为水平 LR
// （n8n 的身份本体是左→右流动），布局契约同步翻转：
//   依赖方向 = x 轴正向，分支 = y 轴展开

/** 测试辅助：构造带 ID 的 ReactFlow 节点 */
function makeNode(id: string, x = 0, y = 0): Node {
  return { id, position: { x, y }, data: { label: id } }
}

function makeEdge(id: string, source: string, target: string): Edge {
  return { id, source, target }
}

describe('applyDagreLayout()', () => {
  it('空图：返回空数组（不抛错）', () => {
    expect(applyDagreLayout([], [])).toEqual([])
  })

  it('单节点：position 被 dagre 重写，类型保持 Node', () => {
    const nodes = [makeNode('a')]
    const out = applyDagreLayout(nodes, [])
    expect(out).toHaveLength(1)
    expect(out[0].id).toBe('a')
    expect(typeof out[0].position.x).toBe('number')
    expect(typeof out[0].position.y).toBe('number')
  })

  it('不修改节点 ID / data，只重写 position', () => {
    const nodes = [makeNode('a'), makeNode('b')]
    const out = applyDagreLayout(nodes, [])
    expect(out[0].id).toBe('a')
    expect(out[1].id).toBe('b')
    expect(out[0].data).toEqual({ label: 'a' })
    expect(out[1].data).toEqual({ label: 'b' })
  })

  it('依赖关系：a→b 布局后 b 应当在 a 右侧（rankdir=LR，n8n 水平流）', () => {
    const nodes = [makeNode('a'), makeNode('b')]
    const edges = [makeEdge('e1', 'a', 'b')]
    const out = applyDagreLayout(nodes, edges)
    const a = out.find((n) => n.id === 'a')!
    const b = out.find((n) => n.id === 'b')!
    // LR 方向：依赖方 x 应大于源
    expect(b.position.x).toBeGreaterThan(a.position.x)
  })

  it('多分支：a→b, a→c 布局后 b/c 在 a 右侧，b/c 同列（x 相同）', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('e1', 'a', 'b'), makeEdge('e2', 'a', 'c')]
    const out = applyDagreLayout(nodes, edges)
    const a = out.find((n) => n.id === 'a')!
    const b = out.find((n) => n.id === 'b')!
    const c = out.find((n) => n.id === 'c')!
    expect(b.position.x).toBeGreaterThan(a.position.x)
    expect(c.position.x).toBeGreaterThan(a.position.x)
    // 同 rank 节点 x 应相同
    expect(b.position.x).toBe(c.position.x)
  })

  it('孤立节点（无任何边）：位置仍被 dagre 写入', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('e1', 'a', 'b')]
    const out = applyDagreLayout(nodes, edges)
    const c = out.find((n) => n.id === 'c')!
    expect(typeof c.position.x).toBe('number')
    expect(typeof c.position.y).toBe('number')
    expect(Number.isFinite(c.position.x)).toBe(true)
    expect(Number.isFinite(c.position.y)).toBe(true)
  })

  it('groupSizes：为指定节点使用自定义尺寸，布局结果有效', () => {
    const nodes = [makeNode('group1'), makeNode('a')]
    const edges = [makeEdge('e1', 'group1', 'a')]
    const groupSizes = new Map([['group1', { width: 400, height: 200 }]])
    const out = applyDagreLayout(nodes, edges, groupSizes)
    expect(out).toHaveLength(2)
    const g = out.find((n) => n.id === 'group1')!
    const a = out.find((n) => n.id === 'a')!
    expect(Number.isFinite(g.position.x)).toBe(true)
    expect(Number.isFinite(a.position.x)).toBe(true)
    // LR 方向：a 应在 group1 右侧
    expect(a.position.x).toBeGreaterThan(g.position.x)
  })

  it('间距增大：ranksep 保证相邻 rank 的水平间距', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('e1', 'a', 'b'), makeEdge('e2', 'a', 'c')]
    const out = applyDagreLayout(nodes, edges)
    const a = out.find((n) => n.id === 'a')!
    const b = out.find((n) => n.id === 'b')!
    // LR：ranksep 作用于 x 轴（dagre center → position = center - width/2）
    expect(b.position.x - a.position.x).toBeGreaterThanOrEqual(60)
  })

  it('groupSizes：未在 map 中的节点仍使用默认尺寸，布局结果有效', () => {
    const nodes = [makeNode('group1'), makeNode('a')]
    const edges = [makeEdge('e1', 'group1', 'a')]
    const groupSizes = new Map([['group1', { width: 400, height: 200 }]])
    const out = applyDagreLayout(nodes, edges, groupSizes)
    // 'a' 不在 groupSizes 中，应使用默认尺寸；布局后 group1 在左，a 在右（LR）
    const g = out.find((n) => n.id === 'group1')!
    const a = out.find((n) => n.id === 'a')!
    expect(Number.isFinite(g.position.x)).toBe(true)
    expect(Number.isFinite(a.position.x)).toBe(true)
    expect(a.position.x).toBeGreaterThan(g.position.x)
  })
})
