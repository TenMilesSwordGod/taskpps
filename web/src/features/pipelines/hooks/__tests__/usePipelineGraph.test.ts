import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePipelineGraph } from '../usePipelineGraph'
import type { PipelineDetail } from '@/types'

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

/** 提取边的 source→target 对（过滤 Start/End 哨兵边） */
function edgePairs(edges: ReturnType<typeof usePipelineGraph>['edges']) {
  return edges
    .filter((e) => e.source !== '__start__' && e.target !== '__end__')
    .map((e) => [e.source, e.target])
}

/** 过滤掉 Start/End 哨兵边 */
function taskEdges(edges: ReturnType<typeof usePipelineGraph>['edges']) {
  return edges.filter((e) => e.source !== '__start__' && e.target !== '__end__')
}

function gatewayId(sourceId: string): string {
  return `gateway-${sourceId}`
}

describe('usePipelineGraph — implicit edges & execution_strategy', () => {
  it('sequential（默认）：无 depends_on 的任务添加隐式顺序边', () => {
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
                { name: 'task-c', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['build.task-a', 'build.task-b'])
    expect(pairs).toContainEqual(['build.task-b', 'build.task-c'])
  })

  it('subpipeline config parallel：无隐式顺序边', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: { execution_strategy: 'parallel', env: {}, retry: 0 },
              depends_on: [],
              tasks: [
                { name: 'task-a', depends_on: [], env: {}, retry: 0 },
                { name: 'task-b', depends_on: [], env: {}, retry: 0 },
                { name: 'task-c', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const pairs = edgePairs(result.current.edges)
    expect(pairs).not.toContainEqual(['build.task-a', 'build.task-b'])
    expect(pairs).not.toContainEqual(['build.task-b', 'build.task-c'])
    expect(taskEdges(result.current.edges)).toHaveLength(0)
  })

  it('pipeline options parallel：无隐式顺序边', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          options: { execution_strategy: 'parallel', env: {}, retry: 0 },
          pipelines: [
            {
              name: 'run',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'task-x', depends_on: [], env: {}, retry: 0 },
                { name: 'task-y', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const pairs = edgePairs(result.current.edges)
    expect(pairs).not.toContainEqual(['run.task-x', 'run.task-y'])
  })

  it('subpipeline config 优先于 pipeline options', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          // pipeline 级别是 parallel
          options: { execution_strategy: 'parallel', env: {}, retry: 0 },
          pipelines: [
            {
              name: 'build',
              // subpipeline 级别覆盖为 sequential
              config: { execution_strategy: 'sequential', env: {}, retry: 0 },
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

    // subpipeline 覆盖为 sequential，应有隐式边
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['build.task-a', 'build.task-b'])
  })

  it('显式 depends_on 边不受 execution_strategy 影响', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: { execution_strategy: 'parallel', env: {}, retry: 0 },
              depends_on: [],
              tasks: [
                { name: 'task-a', depends_on: [], env: {}, retry: 0 },
                { name: 'task-b', depends_on: ['task-a'], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    // 显式边仍然存在
    const depEdge = result.current.edges.find((e) => e.id === 'dep-build.task-a-build.task-b')
    expect(depEdge).toBeDefined()
    // 没有隐式边（只有一个显式边，不含 Start/End 哨兵边）
    expect(taskEdges(result.current.edges)).toHaveLength(1)
  })
})

describe('usePipelineGraph — gateway 合并与边结构', () => {
  it('depends_on 目标 task 有 when 时插入 gateway 并拆分边', () => {
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
                  depends_on: ['task-a'],
                  env: {},
                  retry: 0,
                  when: '${env.RUN_B} == "true"',
                },
              ],
            },
          ],
        }),
      }),
    )

    const sourceId = 'build.task-a'
    const gateway = gatewayId(sourceId)
    const gatewayNode = result.current.nodes.find((n) => n.id === gateway)
    expect(gatewayNode).toBeDefined()
    expect(gatewayNode?.data).toMatchObject({
      isGateway: true,
      sourceTaskName: sourceId,
    })

    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual([sourceId, gateway])
    expect(pairs).toContainEqual([gateway, 'build.task-b'])
    expect(pairs).not.toContainEqual([sourceId, 'build.task-b'])

    const inEdge = result.current.edges.find((e) => e.target === gateway)
    const outEdge = result.current.edges.find((e) => e.source === gateway)
    expect(inEdge?.type).toBe('step')
    expect(outEdge?.type).toBe('step')
    expect(outEdge?.label).toBe('${env.RUN_B} == "true"')
  })

  it('同一 source 多个 when target 时只产生一个 gateway', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'smoke-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_SMOKE}',
                },
                {
                  name: 'perf-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_PERF}',
                },
              ],
            },
          ],
        }),
      }),
    )

    const gatewayNodes = result.current.nodes.filter((n) => n.type === 'whenNode')
    expect(gatewayNodes).toHaveLength(1)

    const sourceId = 'build.setup'
    const gateway = gatewayId(sourceId)
    expect(gatewayNodes[0].id).toBe(gateway)

    const outEdges = result.current.edges.filter((e) => e.source === gateway)
    expect(outEdges).toHaveLength(2)
    expect(outEdges.map((e) => e.target).sort()).toEqual(['build.perf-test', 'build.smoke-test'])
    expect(outEdges.map((e) => e.label).sort()).toEqual(['${RUN_PERF}', '${RUN_SMOKE}'])
    expect(outEdges.every((e) => e.type === 'step')).toBe(true)
  })

  it('gateway → target 的边显示完整 when 条件且不截断', () => {
    const longWhen = '${params.A} == "1" && ${params.B} == "2"'
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
                  depends_on: ['task-a'],
                  env: {},
                  retry: 0,
                  when: longWhen,
                },
              ],
            },
          ],
        }),
      }),
    )

    const gateway = gatewayId('build.task-a')
    const outEdge = result.current.edges.find((e) => e.source === gateway && e.target === 'build.task-b')
    expect(outEdge).toBeDefined()
    expect(outEdge?.label).toBe(longWhen)
  })

  it('隐式顺序边目标 task 有 when 时插入 gateway', () => {
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
                  when: '${params.SKIP} != "yes"',
                },
              ],
            },
          ],
        }),
      }),
    )

    const sourceId = 'build.task-a'
    const gateway = gatewayId(sourceId)
    const gatewayNode = result.current.nodes.find((n) => n.id === gateway)
    expect(gatewayNode).toBeDefined()
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual([sourceId, gateway])
    expect(pairs).toContainEqual([gateway, 'build.task-b'])
    expect(pairs).not.toContainEqual([sourceId, 'build.task-b'])
  })

  it('目标 task 无 when 时不插入 gateway，保留原边', () => {
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
                { name: 'task-b', depends_on: ['task-a'], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    expect(result.current.nodes.find((n) => n.type === 'whenNode')).toBeUndefined()
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['build.task-a', 'build.task-b'])
  })

  it('when 为空字符串时不插入 gateway', () => {
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
                { name: 'task-b', depends_on: ['task-a'], env: {}, retry: 0, when: '' },
              ],
            },
          ],
        }),
      }),
    )

    expect(result.current.nodes.find((n) => n.type === 'whenNode')).toBeUndefined()
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['build.task-a', 'build.task-b'])
  })

  it('跨 subpipeline 目标 firstTask 有 when 时插入 gateway', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [{ name: 'compile', depends_on: [], env: {}, retry: 0 }],
            },
            {
              name: 'deploy',
              config: null,
              depends_on: ['build'],
              tasks: [
                {
                  name: 'push',
                  depends_on: [],
                  env: {},
                  retry: 0,
                  when: '${env.DEPLOY} == "true"',
                },
              ],
            },
          ],
        }),
      }),
    )

    const sourceId = 'build.compile'
    const gateway = gatewayId(sourceId)
    const gatewayNode = result.current.nodes.find((n) => n.id === gateway)
    expect(gatewayNode).toBeDefined()
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual([sourceId, gateway])
    expect(pairs).toContainEqual([gateway, 'deploy.push'])
    expect(pairs).not.toContainEqual([sourceId, 'deploy.push'])
  })

  it('gateway parentId 与 source task 同 group', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'build',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'compile', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'push',
                  depends_on: ['compile'],
                  env: {},
                  retry: 0,
                  when: '${env.DEPLOY} == "true"',
                },
              ],
            },
          ],
        }),
      }),
    )

    const gatewayNode = result.current.nodes.find((n) => n.type === 'whenNode')
    expect(gatewayNode?.parentId).toBe('__group__build')
  })
})

describe('usePipelineGraph — null tasks 安全', () => {
  it('tasks 为 null 时不崩溃', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            { name: 'build', tasks: null, depends_on: [] },
          ],
        }),
      }),
    )
    expect(result.current.nodes).toBeDefined()
    expect(result.current.edges).toBeDefined()
  })

  it('tasks 为空数组时不崩溃', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            { name: 'build', tasks: [], depends_on: [] },
          ],
        }),
      }),
    )
    expect(result.current.nodes).toBeDefined()
    expect(result.current.edges).toBeDefined()
  })

  it('部分 subpipeline tasks 为 null', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            { name: 'build', tasks: [{ name: 'compile', command: 'make', depends_on: [] }], depends_on: [] },
            { name: 'deploy', tasks: null, depends_on: ['build'] },
          ],
        }),
      }),
    )
    // build 有 1 个 task 节点，deploy 没有
    const taskNodes = result.current.nodes.filter((n) => n.type === 'taskNode')
    expect(taskNodes).toHaveLength(1)
    expect(taskNodes[0].id).toBe('build.compile')
  })
})
