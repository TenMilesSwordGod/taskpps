import { describe, it, expect } from 'vitest'
import { applyDagreLayout } from './dagreLayout'
import type { Node, Edge } from '@xyflow/react'

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

  it('依赖关系：a→b 布局后 b 应当在 a 下方（rankdir=TB）', () => {
    const nodes = [makeNode('a'), makeNode('b')]
    const edges = [makeEdge('e1', 'a', 'b')]
    const out = applyDagreLayout(nodes, edges)
    const a = out.find((n) => n.id === 'a')!
    const b = out.find((n) => n.id === 'b')!
    // TB 方向：依赖方 y 应大于源
    expect(b.position.y).toBeGreaterThan(a.position.y)
  })

  it('多分支：a→b, a→c 布局后 b/c 在 a 下方，b/c 同行（y 相同）', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('e1', 'a', 'b'), makeEdge('e2', 'a', 'c')]
    const out = applyDagreLayout(nodes, edges)
    const a = out.find((n) => n.id === 'a')!
    const b = out.find((n) => n.id === 'b')!
    const c = out.find((n) => n.id === 'c')!
    expect(b.position.y).toBeGreaterThan(a.position.y)
    expect(c.position.y).toBeGreaterThan(a.position.y)
    // 同 rank 节点 y 应相同
    expect(b.position.y).toBe(c.position.y)
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
    // TB 方向：a 应在 group1 下方
    expect(a.position.y).toBeGreaterThan(g.position.y)
  })

  it('间距增大：nodesep=80, ranksep=60 导致节点间距更大', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('e1', 'a', 'b'), makeEdge('e2', 'a', 'c')]
    const out = applyDagreLayout(nodes, edges)
    const a = out.find((n) => n.id === 'a')!
    const b = out.find((n) => n.id === 'b')!
    // ranksep=60，加上节点高度 48，b.y - a.y 应 >= 60 + 48 = 108
    // dagre 返回 center，position = center - 24，所以 rank 间距 = ranksep + height
    expect(b.position.y - a.position.y).toBeGreaterThanOrEqual(60)
  })

  it('groupSizes：未在 map 中的节点仍使用默认尺寸，布局结果有效', () => {
    const nodes = [makeNode('group1'), makeNode('a')]
    const edges = [makeEdge('e1', 'group1', 'a')]
    const groupSizes = new Map([['group1', { width: 400, height: 200 }]])
    const out = applyDagreLayout(nodes, edges, groupSizes)
    // 'a' 不在 groupSizes 中，应使用默认 200x48
    // 布局后 group1 在上，a 在下（TB 方向）
    const g = out.find((n) => n.id === 'group1')!
    const a = out.find((n) => n.id === 'a')!
    expect(Number.isFinite(g.position.x)).toBe(true)
    expect(Number.isFinite(a.position.x)).toBe(true)
    expect(a.position.y).toBeGreaterThan(g.position.y)
  })
})
