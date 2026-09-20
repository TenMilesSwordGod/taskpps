import { describe, it, expect } from 'vitest'
import { yamlToNodes } from '../yamlToNodes'
import { nodesToYaml } from '../nodesToYaml'
import type { PipelineDetail } from '@/types'

/**
 * v7 (2026-08): 可视化编辑器保真 —— 画布不可编辑字段必须原样保留。
 *
 * 背景：顶层 post / artifacts 与 subpipeline.artifacts 没有对应的画布控件，
 * 旧实现 nodesToYaml 只重建 name/pipelines/options，进入编辑模式保存一次
 * 就会把它们从 YAML 中静默删除（与 YAML 编辑器同类数据丢失）。
 */
describe('可视化编辑器保真：不可编辑字段', () => {
  it('[P1] 顶层 post/artifacts 与 subpipeline.artifacts 经画布 round-trip 不丢', () => {
    const pipeline: PipelineDetail = {
      name: 'preserve',
      post: {
        on_fail: [{ name: 'cleanup', command: 'echo cleanup', env: {}, retry: 0, depends_on: [] }],
      },
      artifacts: [{ path: 'dist/**' }],
      pipelines: [
        {
          name: 'build',
          depends_on: [],
          artifacts: [{ path: 'build/out/**' }],
          tasks: [{ name: 't1', command: 'echo ok', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    }

    const { nodes, edges } = yamlToNodes(pipeline)
    const { pipeline: out, errors } = nodesToYaml(nodes, edges)

    expect(errors).toEqual([])
    expect(out?.post).toEqual(pipeline.post)
    expect(out?.artifacts).toEqual(pipeline.artifacts)
    expect(out?.pipelines?.[0].artifacts).toEqual(pipeline.pipelines[0].artifacts)
  })

  it('[happy] 没有 post/artifacts 时不产生多余空字段', () => {
    const pipeline: PipelineDetail = {
      name: 'plain',
      pipelines: [
        {
          name: 'build',
          depends_on: [],
          tasks: [{ name: 't1', command: 'echo ok', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    }

    const { nodes, edges } = yamlToNodes(pipeline)
    const { pipeline: out, errors } = nodesToYaml(nodes, edges)

    expect(errors).toEqual([])
    expect(out?.post).toBeUndefined()
    expect(out?.artifacts).toBeUndefined()
    expect(out?.pipelines?.[0].artifacts).toBeUndefined()
  })

  it('[P1] 顶层 options 的 env/timeout 等非画布字段经画布保存不丢', () => {
    const pipeline: PipelineDetail = {
      name: 'cfg-top',
      options: {
        env: { TOKEN: 'abc' },
        retry: 3,
        on_failure: 'continue',
        timeout: 120,
        execution_strategy: 'parallel',
      },
      pipelines: [
        {
          name: 'build',
          depends_on: [],
          tasks: [{ name: 't1', command: 'echo ok', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    }

    const { nodes, edges } = yamlToNodes(pipeline)
    const { pipeline: out, errors } = nodesToYaml(nodes, edges)

    expect(errors).toEqual([])
    expect(out?.options).toEqual(pipeline.options)
  })

  it('[P1] subpipeline.config 的 env/timeout 等非画布字段经画布保存不丢', () => {
    const pipeline: PipelineDetail = {
      name: 'cfg-sub',
      pipelines: [
        {
          name: 'build',
          depends_on: [],
          config: {
            env: { BRANCH: 'main' },
            retry: 2,
            on_failure: 'continue',
            timeout: 30,
            execution_strategy: 'parallel',
          },
          tasks: [{ name: 't1', command: 'echo ok', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    }

    const { nodes, edges } = yamlToNodes(pipeline)
    const { pipeline: out, errors } = nodesToYaml(nodes, edges)

    expect(errors).toEqual([])
    expect(out?.pipelines?.[0].config).toEqual(pipeline.pipelines[0].config)
  })

  it('[P2] config 与 options 同时存在时以 config 为准（与后端一致），options 不被抹掉', () => {
    const pipeline: PipelineDetail = {
      name: 'both-config',
      config: { execution_strategy: 'sequential' },
      options: { execution_strategy: 'parallel', env: { X: '1' } },
      pipelines: [
        {
          name: 'build',
          depends_on: [],
          tasks: [{ name: 't1', command: 'echo ok', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    }

    const { nodes, edges } = yamlToNodes(pipeline)
    // 后端 get_effective_config 优先 config；画布必须展示同一份，否则用户看到的策略与实际执行不一致
    const root = nodes.find((n) => n.id === '__pipeline__')
    expect(root?.data.executionStrategy).toBe('sequential')

    const { pipeline: out, errors } = nodesToYaml(nodes, edges)
    expect(errors).toEqual([])
    expect(out?.config?.execution_strategy).toBe('sequential')
    expect(out?.options).toEqual(pipeline.options)
  })
})
