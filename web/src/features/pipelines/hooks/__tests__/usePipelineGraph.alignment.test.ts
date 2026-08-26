import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePipelineGraph } from '../usePipelineGraph'
import { EDGE } from '../../nodes/nodeTokens'
import type { PipelineDetail } from '@/types'

/**
 * v5 (2026-08): n8n 风格重构配套测试
 * - 组内单链任务应水平成行对齐（消除 dagre 锯齿错位；v11 起流向 LR → 对齐轴为 y）
 * - 分叉/汇合节点保持 dagre 布局（不被强制对齐）
 * - 边样式统一引用 nodeTokens.EDGE（不再散落硬编码）
 */

function makePipeline(overrides: Partial<PipelineDetail> = {}): PipelineDetail {
  return {
    name: 'test-pipeline',
    options: null,
    config: null,
    tasks: null,
    pipelines: [],
    ...overrides,
  }
}

describe('usePipelineGraph — 组内对齐（n8n 风格修复）', () => {
  it('RED: 单链顺序任务的 y 应完全一致（水平成行对齐）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'sync-code', depends_on: [], env: {}, retry: 0 },
                { name: 'list-files', depends_on: [], env: {}, retry: 0 },
                { name: 'upload', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    // v11 (LR): 单链任务共享 y（同行），x 递增（流向）
    const ys = result.current.nodes
      .filter((n) => n.type === 'taskNode')
      .map((n) => n.position.y)

    expect(ys).toHaveLength(3)
    // 单链：三个任务 y 必须相同（链路是一条水平直的锚）
    expect(new Set(ys).size).toBe(1)
  })

  it('RED: 分叉节点（多出边）不被强制对齐，保持 dagre 分支布局', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                // fan-out：a → b, a → c
                {
                  name: 'task-a',
                  depends_on: [],
                  env: {},
                  retry: 0,
                },
                {
                  name: 'task-b',
                  depends_on: ['task-a'],
                  env: {},
                  retry: 0,
                },
                {
                  name: 'task-c',
                  depends_on: ['task-a'],
                  env: {},
                  retry: 0,
                },
              ],
            },
          ],
        }),
      }),
    )

    const byId = new Map(result.current.nodes.map((n) => [n.id, n]))
    const a = byId.get('build.task-a')!
    const b = byId.get('build.task-b')!
    const c = byId.get('build.task-c')!

    // v11 (LR): 分支的两个叶子 y 必须不同（分支纵向展开，否则分支不可读）
    expect(b.position.y).not.toBe(c.position.y)
    // 分叉源 a 居中于两叶之间（y 轴方向）
    expect(a.position.y).toBeGreaterThan(Math.min(b.position.y, c.position.y))
    expect(a.position.y).toBeLessThan(Math.max(b.position.y, c.position.y))
  })

  it('RED: 普通边样式引用 EDGE token（rail 色/宽度一致）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'task-a', depends_on: [], env: {}, retry: 0 },
                { name: 'task-b', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const plainEdge = result.current.edges.find(
      (e) => e.source === 'build.task-a' && e.target === 'build.task-b',
    )
    expect(plainEdge).toBeDefined()
    const style = plainEdge!.style as { stroke?: string; strokeWidth?: number }
    expect(style.stroke).toBe(EDGE.rail.stroke)
    expect(style.strokeWidth).toBe(EDGE.rail.strokeWidth)
  })

  it('RED: START 出边引用 EDGE.start token', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [{ name: 'task-a', depends_on: [], env: {}, retry: 0 }],
            },
          ],
        }),
      }),
    )

    const startEdge = result.current.edges.find((e) => e.source === '__start__')
    expect(startEdge).toBeDefined()
    const style = startEdge!.style as { stroke?: string }
    expect(style.stroke).toBe(EDGE.start.stroke)
  })

  it('RED: when 条件链中的 decision 节点应与任务同行（消除 Z 字绕行）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'task-a', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'task-b',
                  depends_on: [],
                  env: {},
                  retry: 0,
                  when: '${env.ENABLE} == "1"',
                },
                // task-c 保证 task-b 不是末节点（覆盖 alt 边场景）
                { name: 'task-c', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const byId = new Map(result.current.nodes.map((n) => [n.id, n]))
    const a = byId.get('build.task-a')!
    const decisionId = `decision-build.task-a-build.task-b`
    const d = byId.get(decisionId)!
    // v11 (LR): decision 与唯一前驱 task-a 共享 y → task-a → decision 入边为直线
    expect(d.position.y).toBe(a.position.y)
  })

  it('RED: 有依赖关系的两分组，下游组左缘不早于上游组右缘（依赖边不逆向爬升）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              // 复刻截图场景：upstream 含 when 条件链 → decision 使实际渲染宽度
              // 超过 dagre 排布时的估算宽度，组右缘侵入下游区域
              name: 'upstream',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'u1', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'u2',
                  depends_on: [],
                  env: {},
                  retry: 0,
                  when: '${env.ENABLE_U2} == "1"',
                },
                { name: 'u3', depends_on: [], env: {}, retry: 0 },
              ],
            },
            {
              name: 'downstream',
              config: null,
              depends_on: ['upstream'],
              tasks: [{ name: 'd1', depends_on: [], env: {}, retry: 0 }],
            },
          ],
        }),
      }),
    )

    const groups = result.current.nodes.filter((n) => n.type === 'subpipelineGroup')
    const up = groups.find((n) => n.id === '__group__upstream')!
    const down = groups.find((n) => n.id === '__group__downstream')!
    const upRight = up.position.x + ((up.style as { width?: number }).width ?? 0)
    // v11 (LR): downstream.left 必须在 upstream.right 之右，否则 cross-sub 边逆向爬升
    expect(down.position.x).toBeGreaterThanOrEqual(upRight)
  })

  it('RED: 所有节点携带顶层显式 width/height（MiniMap nodeHasDimensions 依赖它）', () => {
    // 根因：受控模式（无 onNodesChange）下 dimensions change 不写回 userNode.measured，
    // MiniMap 的 nodeHasDimensions(userNode) 永远 false → 小地图零节点图形（全白）
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                {
                  name: 'task-a',
                  depends_on: [],
                  env: {},
                  retry: 0,
                  when: '${env.X} == "1"',
                  post: { on_fail: [{ name: 'cleanup', command: 'echo' }] },
                },
                { name: 'task-b', depends_on: [], env: {}, retry: 0 },
              ],
            },
            {
              name: 'downstream',
              config: null,
              depends_on: ['build'],
              tasks: [],
            },
          ],
        }),
      }),
    )

    expect(result.current.nodes.length).toBeGreaterThan(0)
    for (const n of result.current.nodes) {
      expect(n.width, `节点 ${n.id} 缺顶层 width`).toBeGreaterThan(0)
      expect(n.height, `节点 ${n.id} 缺顶层 height`).toBeGreaterThan(0)
    }
  })
})

