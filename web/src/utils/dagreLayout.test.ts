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
})
