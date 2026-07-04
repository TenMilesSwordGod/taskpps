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

/** 生成决策节点 id */
function decisionId(sourceId: string, targetId: string): string {
  return `decision-${sourceId}-${targetId}`
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

describe('usePipelineGraph — decisionNode 决策节点与边结构', () => {
  it('depends_on 目标 task 有 when 时创建决策节点，source→decision→(yes)→target', () => {
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
              ],
            },
          ],
        }),
      }),
    )

    const did = decisionId('build.setup', 'build.smoke-test')

    // 创建了决策节点
    const dn = result.current.nodes.find((n) => n.id === did)
    expect(dn).toBeDefined()
    expect(dn?.type).toBe('decisionNode')

    // source → decision 边（无 sourceHandle，普通样式）
    const srcEdge = result.current.edges.find((e) => e.source === 'build.setup' && e.target === did)
    expect(srcEdge).toBeDefined()
    expect(srcEdge?.sourceHandle).toBeUndefined()

    // decision →(yes)→ target 边
    const yesEdge = result.current.edges.find((e) => e.source === did && e.target === 'build.smoke-test')
    expect(yesEdge).toBeDefined()
    expect(yesEdge?.sourceHandle).toBe('yes')
    expect(yesEdge?.label).toBe('yes')
    expect((yesEdge?.style as { stroke?: string })?.stroke).toBe('#16A34A')
  })

  it('条件任务有下游时，不创建 no 边（no 路径由菱形标注隐含）', () => {
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
                  name: 'final',
                  depends_on: ['smoke-test'],
                  env: {},
                  retry: 0,
                },
              ],
            },
          ],
        }),
      }),
    )

    const did = decisionId('build.setup', 'build.smoke-test')

    // 不应有 no 边（no 路径隐含，不画边避免交叉）
    const noEdges = result.current.edges.filter(
      (e) => e.source === did && e.sourceHandle === 'no',
    )
    expect(noEdges).toHaveLength(0)

    // smoke-test → final 直连边仍存在
    const directEdge = result.current.edges.find(
      (e) => e.source === 'build.smoke-test' && e.target === 'build.final',
    )
    expect(directEdge).toBeDefined()
  })

  it('同一 source 多个 when target 时各创建独立决策节点', () => {
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

    const did1 = decisionId('build.setup', 'build.smoke-test')
    const did2 = decisionId('build.setup', 'build.perf-test')

    // 两个独立决策节点
    expect(result.current.nodes.find((n) => n.id === did1)).toBeDefined()
    expect(result.current.nodes.find((n) => n.id === did2)).toBeDefined()

    // 各自有 yes 边
    const yes1 = result.current.edges.find((e) => e.source === did1 && e.target === 'build.smoke-test')
    const yes2 = result.current.edges.find((e) => e.source === did2 && e.target === 'build.perf-test')
    expect(yes1?.sourceHandle).toBe('yes')
    expect(yes2?.sourceHandle).toBe('yes')
  })

  it('决策节点 data.when 等于完整条件表达式', () => {
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

    const did = decisionId('build.task-a', 'build.task-b')
    const dn = result.current.nodes.find((n) => n.id === did)
    expect((dn?.data as { when?: string })?.when).toBe(longWhen)
  })

  it('隐式顺序边目标 task 有 when 时也创建决策节点', () => {
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

    const did = decisionId('build.task-a', 'build.task-b')
    const dn = result.current.nodes.find((n) => n.id === did)
    expect(dn).toBeDefined()
    expect(dn?.type).toBe('decisionNode')

    const yesEdge = result.current.edges.find((e) => e.source === did && e.target === 'build.task-b')
    expect(yesEdge?.sourceHandle).toBe('yes')
  })

  it('目标 task 无 when 时不插入决策节点，保留原边', () => {
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

    expect(result.current.nodes.find((n) => n.type === 'decisionNode')).toBeUndefined()
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['build.task-a', 'build.task-b'])
  })

  it('when 为空字符串时不插入决策节点', () => {
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

    expect(result.current.nodes.find((n) => n.type === 'decisionNode')).toBeUndefined()
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['build.task-a', 'build.task-b'])
  })

  it('跨 subpipeline 目标 firstTask 有 when 时创建决策节点', () => {
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

    const did = 'decision-cross-build-deploy'
    const dn = result.current.nodes.find((n) => n.id === did)
    expect(dn).toBeDefined()
    expect(dn?.type).toBe('decisionNode')

    // 跨 group 拓扑边：source group → target group
    const crossEdge = result.current.edges.find(
      (e) => e.id === 'cross-sub-build-deploy',
    )
    expect(crossEdge).toBeDefined()
    expect(crossEdge?.source).toBe('__group__build')
    expect(crossEdge?.target).toBe('__group__deploy')

    // decision →(yes)→ push
    const yesEdge = result.current.edges.find((e) => e.source === did && e.target === 'deploy.push')
    expect(yesEdge?.sourceHandle).toBe('yes')
    expect(yesEdge?.label).toBe('yes')
    expect((yesEdge?.style as { stroke?: string })?.stroke).toBe('#16A34A')
  })

  it('决策节点 parentId 与 source task 同 group', () => {
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

    const did = decisionId('build.compile', 'build.push')
    const dn = result.current.nodes.find((n) => n.id === did)
    const sourceNode = result.current.nodes.find((n) => n.id === 'build.compile')
    expect(dn?.parentId).toBe(sourceNode?.parentId)
    expect(dn?.parentId).toBe('__group__build')
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

describe('usePipelineGraph — group 垂直不重叠', () => {
  it('链式 subpipeline 的 group 不应垂直重叠', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'sub1',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'task-a', depends_on: [], env: {}, retry: 0 },
                { name: 'task-b', depends_on: ['task-a'], env: {}, retry: 0 },
              ],
            },
            {
              name: 'sub2',
              config: null,
              depends_on: ['sub1'],
              tasks: [
                { name: 'task-c', depends_on: [], env: {}, retry: 0 },
                { name: 'task-d', depends_on: ['task-c'], env: {}, retry: 0 },
              ],
            },
            {
              name: 'sub3',
              config: null,
              depends_on: ['sub2'],
              tasks: [
                { name: 'task-e', depends_on: [], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const groups = result.current.nodes.filter((n) => n.type === 'subpipelineGroup')
    expect(groups.length).toBe(3)

    // 检查每对 x 范围有重叠的 group 是否垂直重叠
    for (let i = 0; i < groups.length; i++) {
      for (let j = i + 1; j < groups.length; j++) {
        const a = groups[i]
        const b = groups[j]
        const aW = (a.style as { width?: number })?.width ?? 200
        const aH = (a.style as { height?: number })?.height ?? 100
        const bW = (b.style as { width?: number })?.width ?? 200
        const bH = (b.style as { height?: number })?.height ?? 100

        const xOverlap = !(a.position.x + aW <= b.position.x || b.position.x + bW <= a.position.x)
        if (!xOverlap) continue

        const aBottom = a.position.y + aH
        const bBottom = b.position.y + bH
        const yOverlap = !(aBottom <= b.position.y || bBottom <= a.position.y)
        expect(yOverlap).toBe(false)
      }
    }
  })
})
