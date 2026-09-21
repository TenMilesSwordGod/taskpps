import { describe, it, expect } from 'vitest'
import { parseYamlToPipeline } from '../yamlParser'

/**
 * v7 (2026-08): YAML 重复定义校验 —— 与后端 pydantic 校验对齐。
 *
 * 背景：后端 DAG 用 {task.name: task} 建图、subpipeline 依赖用
 * get_subpipeline_by_name 命中第一个。重复名称会静默覆盖定义 / 漏跑任务 /
 * 报「循环依赖」。前端必须在编辑时就给出明确错误，而不是等保存成功后运行失败。
 */
describe('YAML 重复定义校验', () => {
  it('[P1] 同一 subpipeline 内重复 task name 必须校验失败', () => {
    const yaml = [
      'name: dup-task',
      'pipelines:',
      '  - name: build',
      '    tasks:',
      '      - name: compile',
      '        command: echo 1',
      '      - name: compile',
      '        command: echo 2',
    ].join('\n')

    const result = parseYamlToPipeline(yaml)
    expect(result.success).toBe(false)
    expect(result.error?.message).toContain('compile')
    expect(result.error?.path).toBe('pipelines[0].tasks')
  })

  it('[P1] 重复 subpipeline name 必须校验失败', () => {
    const yaml = [
      'name: dup-sub',
      'pipelines:',
      '  - name: build',
      '    tasks:',
      '      - name: t1',
      '        command: echo 1',
      '  - name: build',
      '    tasks:',
      '      - name: t2',
      '        command: echo 2',
    ].join('\n')

    const result = parseYamlToPipeline(yaml)
    expect(result.success).toBe(false)
    expect(result.error?.message).toContain('名称重复')
    expect(result.error?.path).toBe('pipelines[1].name')
  })

  it('[P1] 顶层 tasks 与 pipelines 同时存在必须校验失败', () => {
    const yaml = [
      'name: both-forms',
      'tasks:',
      '  - name: top-task',
      '    command: echo top',
      'pipelines:',
      '  - name: sub',
      '    tasks:',
      '      - name: sub-task',
      '        command: echo sub',
    ].join('\n')

    const result = parseYamlToPipeline(yaml)
    expect(result.success).toBe(false)
    expect(result.error?.message).toContain('不能同时使用')
  })

  it('[P1] 顶层 tasks 内重复 task name 必须校验失败', () => {
    const yaml = [
      'name: dup-top',
      'tasks:',
      '  - name: step',
      '    command: echo 1',
      '  - name: step',
      '    command: echo 2',
    ].join('\n')

    const result = parseYamlToPipeline(yaml)
    expect(result.success).toBe(false)
    expect(result.error?.message).toContain('step')
    expect(result.error?.path).toBe('tasks')
  })

  it('[P2] 重复 mapping key（重复 env 变量）由 js-yaml 直接报错', () => {
    const yaml = [
      'name: dup-key',
      'config:',
      '  env:',
      '    TOKEN: first',
      '    TOKEN: second',
      'tasks:',
      '  - name: t1',
      '    command: echo ${env.TOKEN}',
    ].join('\n')

    const result = parseYamlToPipeline(yaml)
    expect(result.success).toBe(false)
  })
})
