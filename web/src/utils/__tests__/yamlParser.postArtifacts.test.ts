import { describe, it, expect } from 'vitest'
import { parseYamlToPipeline, pipelineToYaml } from '../yamlParser'

/**
 * v7 (2026-08): 顶层 post / artifacts 保真。
 *
 * 背景：PipelineDetail 类型包含 post（失败/成功钩子）与 artifacts（顶层产物声明），
 * 后端 PipelineYAML 也支持并会执行它们。但 parseYamlToPipeline 不拷贝这两个字段，
 * pipelineToYaml 也不输出 —— 用户打开 YAML 编辑器时它们已从文本中消失，
 * 任何一次保存都会把这两个功能从磁盘上静默删除。
 */
describe('顶层 post / artifacts 保真', () => {
  const yamlWithPostAndArtifacts = [
    'name: with-post',
    'post:',
    '  on_fail:',
    '    - name: cleanup',
    '      command: echo cleanup',
    '  always:',
    '    - name: notify',
    '      command: echo notify',
    'artifacts:',
    '  - path: dist/**',
    'tasks:',
    '  - name: t1',
    '    command: echo ok',
  ].join('\n')

  it('[P1] parseYamlToPipeline 必须保留顶层 post 与 artifacts', () => {
    const result = parseYamlToPipeline(yamlWithPostAndArtifacts)
    expect(result.success).toBe(true)
    expect(result.pipeline?.post?.on_fail?.[0]?.name).toBe('cleanup')
    expect(result.pipeline?.post?.always?.[0]?.name).toBe('notify')
    expect(result.pipeline?.artifacts?.[0]?.path).toBe('dist/**')
  })

  it('[P1] pipelineToYaml 必须输出顶层 post 与 artifacts', () => {
    const result = parseYamlToPipeline(yamlWithPostAndArtifacts)
    expect(result.success).toBe(true)

    const serialized = pipelineToYaml(result.pipeline!)
    expect(serialized).toContain('post:')
    expect(serialized).toContain('cleanup')
    expect(serialized).toContain('notify')
    expect(serialized).toContain('artifacts:')
    expect(serialized).toContain('dist/**')
  })

  it('[P1] 解析→序列化 round-trip 不丢顶层 post / artifacts', () => {
    const result = parseYamlToPipeline(yamlWithPostAndArtifacts)
    const reparsed = parseYamlToPipeline(pipelineToYaml(result.pipeline!))
    expect(reparsed.success).toBe(true)
    expect(reparsed.pipeline?.post).toEqual(result.pipeline?.post)
    expect(reparsed.pipeline?.artifacts).toEqual(result.pipeline?.artifacts)
  })
})
