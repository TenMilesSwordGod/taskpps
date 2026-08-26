import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { usePipelineGraph } from '../usePipelineGraph'
import { EDGE, INK, NODE_SIZE } from '../../nodes/nodeTokens'
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

/** 判断是否为 group 拓扑边（START→group.top、group.bottom→END、group↔group 等经过 group handle 的边） */
function isGroupTopologyEdge(e: { source: string; target: string }) {
  return e.source.startsWith('__group__') || e.target.startsWith('__group__')
}

/** 提取边的 source→target 对（过滤哨兵边和 group 拓扑边，只保留 task↔task 边） */
function edgePairs(edges: ReturnType<typeof usePipelineGraph>['edges']) {
  return edges
    .filter(
      (e) =>
        e.source !== '__start__' &&
        e.target !== '__end__' &&
        !isGroupTopologyEdge(e),
    )
    .map((e) => [e.source, e.target])
}

/** 过滤掉 Start/End 哨兵边和 group 拓扑边，只保留 task↔task 边 */
function taskEdges(edges: ReturnType<typeof usePipelineGraph>['edges']) {
  return edges.filter(
    (e) =>
      e.source !== '__start__' &&
      e.target !== '__end__' &&
      !isGroupTopologyEdge(e),
  )
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
    // 没有隐式边（只有一条显式 dep 边；其余是 START→IN、IN→首task、末task→OUT、OUT→END 等拓扑边）
    const taskToTaskEdges = taskEdges(result.current.edges)
    expect(taskToTaskEdges).toHaveLength(1)
    expect(taskToTaskEdges[0].id).toBe('dep-build.task-a-build.task-b')
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
    expect((yesEdge?.style as { stroke?: string })?.stroke).toBe(EDGE.yes.stroke)
  })

  it('条件任务有下游时，no 边连到下游任务（自然垂直路径）', () => {
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

    // no 边汇入 group.exit handle（底部 target），与 group.bottom（source → END）同位置
    const noEdge = result.current.edges.find(
      (e) => e.source === did && e.sourceHandle === 'no',
    )
    expect(noEdge).toBeDefined()
    expect(noEdge?.target).toBe('__group__build')
    expect(noEdge?.targetHandle).toBe('exit')
    expect(noEdge?.label).toBe('no')

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
    expect((yesEdge?.style as { stroke?: string })?.stroke).toBe(EDGE.yes.stroke)
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

describe('usePipelineGraph — alt 边补全（when 孤立 task）', () => {
  it('带 when 且无出边的 task 补一条 alt 边到 group 输出点（bottom handle）', () => {
    // 复现 pipelines/debug/06-conditional.yaml 场景
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'smoke-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_SMOKE} == true',
                },
                {
                  name: 'perf-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_PERF} == true',
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

    // perf-test 是带 when 且无出边的孤立 task → 应有 alt 边汇入 group.exit handle
    const altEdge = result.current.edges.find(
      (e) => e.source === 'main.perf-test' && e.label === 'alt',
    )
    expect(altEdge).toBeDefined()
    expect(altEdge?.target).toBe('__group__main')
    expect(altEdge?.targetHandle).toBe('exit')
    // v11: bezier 顺流曲线（LR）
    expect(altEdge?.type).toBe('default')
    expect((altEdge?.style as { stroke?: string })?.stroke).toBe(EDGE.railSoft.stroke)
    expect((altEdge?.style as { strokeWidth?: number })?.strokeWidth).toBe(EDGE.railSoft.strokeWidth)
    expect((altEdge?.style as { strokeDasharray?: string })?.strokeDasharray).toBe(EDGE.railSoft.strokeDasharray)
    // v11: label 文字色引用 INK.textSecondary（随 token 逐步迁移到 n8n 副标题色）
    expect((altEdge?.labelStyle as { fill?: string })?.fill).toBe(INK.textSecondary)
    expect((altEdge?.labelBgStyle as { fill?: string })?.fill).toBe('#F8FAFC')
  })

  it('带 when 但有显式出边的 task 不补 alt 边', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'smoke-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_SMOKE} == true',
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

    // smoke-test 有出边（smoke-test → final），不应有 alt 边
    const altEdge = result.current.edges.find(
      (e) => e.source === 'main.smoke-test' && e.label === 'alt',
    )
    expect(altEdge).toBeUndefined()
  })

  it('无 when 的孤立 task 不补 alt 边', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'lonely',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                },
              ],
            },
          ],
        }),
      }),
    )

    // lonely 无 when，即使没有出边也不补 alt 边
    const altEdge = result.current.edges.find(
      (e) => e.source === 'main.lonely' && e.label === 'alt',
    )
    expect(altEdge).toBeUndefined()
  })

  it('alt 边 id 唯一且可识别', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'perf-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_PERF} == true',
                },
              ],
            },
          ],
        }),
      }),
    )

    const altEdge = result.current.edges.find(
      (e) => e.id === 'alt-main.perf-test-__group__main',
    )
    expect(altEdge).toBeDefined()
    expect(altEdge?.source).toBe('main.perf-test')
    expect(altEdge?.target).toBe('__group__main')
    expect(altEdge?.targetHandle).toBe('exit')
  })
})

describe('usePipelineGraph — no 边构建（决策节点跳过路径）', () => {
  it('no 边连到下游任务（有下游时连下游，自然垂直路径）', () => {
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
                  when: '${RUN_SMOKE} == true',
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
    const noEdge = result.current.edges.find(
      (e) => e.source === did && e.sourceHandle === 'no',
    )
    expect(noEdge).toBeDefined()
    // no 边汇入 group.exit handle
    expect(noEdge?.target).toBe('__group__build')
    expect(noEdge?.targetHandle).toBe('exit')
    expect(noEdge?.label).toBe('no')
    expect(noEdge?.sourceHandle).toBe('no')
  })

  it('条件任务无下游时，no 边连到 group exit（确保 flow 完整）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'perf-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_PERF} == true',
                },
              ],
            },
          ],
        }),
      }),
    )

    const did = decisionId('main.setup', 'main.perf-test')
    const noEdge = result.current.edges.find(
      (e) => e.source === did && e.sourceHandle === 'no',
    )
    // 无下游时 no 边必须存在，连到 group exit，确保条件全 no 时 flow 不中断
    expect(noEdge).toBeDefined()
    expect(noEdge?.target).toBe('__group__main')
    expect(noEdge?.targetHandle).toBe('exit')
    expect(noEdge?.label).toBe('no')
  })

  it('06-conditional.yaml 场景：所有 decision 的 no 边都连到 group exit', () => {
    // 复现 pipelines/debug/06-conditional.yaml 场景
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                {
                  name: 'smoke-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_SMOKE} == true',
                },
                {
                  name: 'perf-test',
                  depends_on: ['setup'],
                  env: {},
                  retry: 0,
                  when: '${RUN_PERF} == true',
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

    const didSmoke = decisionId('main.setup', 'main.smoke-test')
    const didPerf = decisionId('main.setup', 'main.perf-test')

    // smoke-test 有下游 final → no 边汇入 group.exit handle
    const noSmoke = result.current.edges.find(
      (e) => e.source === didSmoke && e.sourceHandle === 'no',
    )
    expect(noSmoke).toBeDefined()
    expect(noSmoke?.target).toBe('__group__main')
    expect(noSmoke?.targetHandle).toBe('exit')

    // perf-test 无下游 → no 边也必须存在，连到 group exit
    const noPerf = result.current.edges.find(
      (e) => e.source === didPerf && e.sourceHandle === 'no',
    )
    expect(noPerf).toBeDefined()
    expect(noPerf?.target).toBe('__group__main')
    expect(noPerf?.targetHandle).toBe('exit')
  })

  it('no 边样式为灰色实线 bezier（区别于 yes 的绿色和 alt 的浅灰）', () => {
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
                  when: '${RUN_SMOKE} == true',
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
    const noEdge = result.current.edges.find(
      (e) => e.source === did && e.sourceHandle === 'no',
    )
    expect(noEdge).toBeDefined()
    // v11: bezier 顺流曲线（LR）
    expect(noEdge?.type).toBe('default')
    // no 边使用 RAIL_STYLE（灰色实线）
    expect((noEdge?.style as { stroke?: string })?.stroke).toBe(EDGE.rail.stroke)
    expect((noEdge?.style as { strokeDasharray?: string })?.strokeDasharray).toBeUndefined()
  })
})

describe('usePipelineGraph — group 水平不重叠', () => {
  it('链式 subpipeline 的 group 不应水平重叠', () => {
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

    // v11 (LR): 检查每对 y 范围有重叠的 group 是否水平重叠
    for (let i = 0; i < groups.length; i++) {
      for (let j = i + 1; j < groups.length; j++) {
        const a = groups[i]
        const b = groups[j]
        const aW = (a.style as { width?: number })?.width ?? 200
        const aH = (a.style as { height?: number })?.height ?? 100
        const bW = (b.style as { width?: number })?.width ?? 200
        const bH = (b.style as { height?: number })?.height ?? 100

        const yOverlap = !(a.position.y + aH <= b.position.y || b.position.y + bH <= a.position.y)
        if (!yOverlap) continue

        const aRight = a.position.x + aW
        const bRight = b.position.x + bW
        const xOverlap = !(aRight <= b.position.x || bRight <= a.position.x)
        expect(xOverlap).toBe(false)
      }
    }
  })
})

describe('usePipelineGraph — START/END 通过 group IN/OUT handle', () => {
  it('根 group 的 START → group.top(绿) → group.top-out(灰) → 首 task', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                { name: 'final', depends_on: ['setup'], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const gid = '__group__main'

    // START → group.top（绿色外部边）
    const startEdge = result.current.edges.find((e) => e.id === `start-to-${gid}`)
    expect(startEdge).toBeDefined()
    expect(startEdge?.source).toBe('__start__')
    expect(startEdge?.target).toBe(gid)
    expect(startEdge?.targetHandle).toBe('top')
    expect((startEdge?.style as { stroke?: string })?.stroke).toBe('#10B981')

    // group.top-out → 首 task（灰色内部边）
    const enterEdge = result.current.edges.find((e) => e.id === `enter-${gid}`)
    expect(enterEdge).toBeDefined()
    expect(enterEdge?.source).toBe(gid)
    expect(enterEdge?.sourceHandle).toBe('top-out')
    expect(enterEdge?.target).toBe('main.setup')
    expect((enterEdge?.style as { stroke?: string })?.stroke).toBe(EDGE.rail.stroke)
  })

  it('叶子 group 的末 task → group.exit → group.bottom → END', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'main',
              config: null,
              depends_on: [],
              tasks: [
                { name: 'setup', depends_on: [], env: {}, retry: 0 },
                { name: 'final', depends_on: ['setup'], env: {}, retry: 0 },
              ],
            },
          ],
        }),
      }),
    )

    const gid = '__group__main'

    // 末 task → group.exit（底部 target handle）
    const outEdge = result.current.edges.find((e) => e.id === `${gid}-out`)
    expect(outEdge).toBeDefined()
    expect(outEdge?.source).toBe('main.final')
    expect(outEdge?.target).toBe(gid)
    expect(outEdge?.targetHandle).toBe('exit')

    // group.bottom（底部 source handle）→ END
    const endEdge = result.current.edges.find((e) => e.id === `${gid}-to-end`)
    expect(endEdge).toBeDefined()
    expect(endEdge?.source).toBe(gid)
    expect(endEdge?.sourceHandle).toBe('bottom')
    expect(endEdge?.target).toBe('__end__')
  })
})

describe('usePipelineGraph — 健壮性（孤儿边/重复边）', () => {
  it('空 subpipeline + subpipeline 级 post：不产生 source 为空字符串的孤儿边', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'empty',
              tasks: null,
              depends_on: [],
              post: {
                always: [{ name: 'cleanup', depends_on: [], env: {}, retry: 0 }],
              },
            },
          ],
        }),
      }),
    )
    const nodeIds = new Set(result.current.nodes.map((n) => n.id))
    const orphanSources = result.current.edges
      .filter((e) => !nodeIds.has(e.source))
      .map((e) => e.id)
    expect(orphanSources).toEqual([])
  })

  it('depends_on 引用不存在的 task：跳过该孤儿边，不影响其他边', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'sub1',
              tasks: [
                { name: 'a', depends_on: ['nonexistent'], env: {}, retry: 0 },
                { name: 'b', depends_on: [], env: {}, retry: 0 },
              ],
              depends_on: [],
            },
          ],
        }),
      }),
    )
    const nodeIds = new Set(result.current.nodes.map((n) => n.id))
    const orphanSources = result.current.edges
      .filter((e) => !nodeIds.has(e.source))
      .map((e) => e.id)
    expect(orphanSources).toEqual([])
    // 隐式顺序边 a→b 仍应存在
    const pairs = edgePairs(result.current.edges)
    expect(pairs).toContainEqual(['sub1.a', 'sub1.b'])
  })

  it('sub 依赖多个 dep + 无 when：enter 边只创建一次（无重复 id）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'sub1',
              tasks: [{ name: 'a', depends_on: [], env: {}, retry: 0 }],
              depends_on: [],
            },
            {
              name: 'sub2',
              tasks: [{ name: 'b', depends_on: [], env: {}, retry: 0 }],
              depends_on: [],
            },
            {
              name: 'sub3',
              tasks: [{ name: 'c', depends_on: [], env: {}, retry: 0 }],
              depends_on: ['sub1', 'sub2'],
            },
          ],
        }),
      }),
    )
    const idCounts = new Map<string, number>()
    for (const e of result.current.edges) {
      idCounts.set(e.id, (idCounts.get(e.id) ?? 0) + 1)
    }
    const dupIds = [...idCounts.entries()].filter(([, c]) => c > 1)
    expect(dupIds).toEqual([])

    // enter-__group__sub3 恰好存在一次
    const enterEdges = result.current.edges.filter((e) => e.id === 'enter-__group__sub3')
    expect(enterEdges).toHaveLength(1)
  })
})

// v9 (2026-08): 连线正交化修复配套测试 —— 消除 bezier 弧钩出组与并行组连线横穿。
// v11 (2026-08): 随 LR 流向翻转 —— 链中轴与组 handle 中轴（top:50%）对齐；
// START/END 贴 root/leaf group 联合包围盒左/右缘垂直居中。
describe('usePipelineGraph — 组内链居中与 START/END 联合中心对齐', () => {
  it('组内任务链垂直居中：链中轴与组 handle 中轴（top:50%）对齐', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              // 长组名 → header 决定组宽 > 任务区宽，
              // 复现"链贴顶、handle 居中"的错位场景（v11: 视轴翻转，链贴左 → 居中）
              name: 'Sync Automation code',
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

    const group = result.current.nodes.find((n) => n.type === 'subpipelineGroup')!
    const firstTask = result.current.nodes.find((n) => n.id === 'Sync Automation code.task-a')!
    const groupH = (group.style as { height?: number })?.height ?? group.height ?? 0
    // v11 (LR): 链的垂直中轴应落在组高中点（±1px 容差），enter/exit 边即为纯水平直线
    const chainCenterY = firstTask.position.y + NODE_SIZE.TASK_H / 2
    expect(Math.abs(chainCenterY - groupH / 2)).toBeLessThanOrEqual(1)
  })

  it('START/END 贴 root/leaf group 联合包围盒左右缘垂直居中（并行双组不横穿）', () => {
    const { result } = renderHook(() =>
      usePipelineGraph({
        pipeline: makePipeline({
          pipelines: [
            {
              name: 'alpha',
              config: null,
              depends_on: [],
              tasks: [{ name: 't1', depends_on: [], env: {}, retry: 0 }],
            },
            {
              name: 'beta',
              config: null,
              depends_on: [],
              tasks: [{ name: 't2', depends_on: [], env: {}, retry: 0 }],
            },
          ],
        }),
      }),
    )

    const groups = result.current.nodes.filter((n) => n.type === 'subpipelineGroup')
    expect(groups.length).toBe(2)
    const minX = Math.min(...groups.map((g) => g.position.x))
    const maxX = Math.max(
      ...groups.map((g) => g.position.x + ((g.style as { width?: number })?.width ?? 200)),
    )
    const minY = Math.min(...groups.map((g) => g.position.y))
    const maxY = Math.max(
      ...groups.map((g) => g.position.y + ((g.style as { height?: number })?.height ?? 100)),
    )
    const jointCenterY = (minY + maxY) / 2

    const start = result.current.nodes.find((n) => n.id === '__start__')!
    const end = result.current.nodes.find((n) => n.id === '__end__')!
    // v11 (LR): START 在左缘外侧、END 在右缘外侧；两者垂直中心对齐联合包围盒中轴
    const startCenterX = start.position.x + NODE_SIZE.SENTINEL_START_W / 2
    const endCenterX = end.position.x + NODE_SIZE.SENTINEL_END_W / 2
    expect(startCenterX).toBeLessThan(minX)
    expect(endCenterX).toBeGreaterThan(maxX)
    expect(Math.abs(start.position.y + NODE_SIZE.SENTINEL_H / 2 - jointCenterY)).toBeLessThanOrEqual(1)
    expect(Math.abs(end.position.y + NODE_SIZE.SENTINEL_H / 2 - jointCenterY)).toBeLessThanOrEqual(1)
  })
})
