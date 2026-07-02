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

/** 提取边的 source→target 对 */
function edgePairs(edges: ReturnType<typeof usePipelineGraph>['edges']) {
  return edges.map((e) => [e.source, e.target])
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
    expect(result.current.edges).toHaveLength(0)
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
    // 没有隐式边（只有一个显式边）
    expect(result.current.edges).toHaveLength(1)
  })
})
