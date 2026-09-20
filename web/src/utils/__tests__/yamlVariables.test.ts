import { describe, it, expect } from 'vitest'
import {
  buildVariableIndex,
  findVariableAt,
  resolveVariableInfo,
  type AgentVariableSource,
  type CredentialVariableSource,
} from '../yamlVariables'

/**
 * YAML 变量悬浮解析单测（2026-09）。
 *
 * 契约：编辑器里 ${...} 悬浮展示"当前 YAML 上下文"里能确定的信息：
 * - env/params 取 YAML 内定义值（按光标所在 task/subpipeline 作用域就近解析）
 * - agent/credential 由调用方注入项目配置（密码类不回传，只说明）
 * - task.output / 内置变量 / 制品等运行时才知道的，明确标注"运行时可用"
 */

const YAML_TEXT = `name: test
env:
  ROOT_ONLY: root-value
params:
  - name: VERSION_TAG
    label: 版本标签
    default: v2.0.0
  - name: NO_DEFAULT
    label: 无默认值
options:
  env:
    APP_ENV: options-staging
pipelines:
  - name: build
    config:
      env:
        APP_ENV: sub-staging
        SUB_ONLY: sub-value
    tasks:
      - name: compile
        command: echo \${env.APP_ENV} \${env.SUB_ONLY} \${env.ROOT_ONLY} \${env.UNDEFINED}
        env:
          APP_ENV: task-staging
      - name: package
        command: echo \${env.APP_ENV}
`

/** 找到文本中指定片段所在行号（1-indexed） */
function lineOf(fragment: string): number {
  const idx = YAML_TEXT.split('\n').findIndex((l) => l.includes(fragment))
  expect(idx).toBeGreaterThanOrEqual(0)
  return idx + 1
}

const index = buildVariableIndex(YAML_TEXT)

describe('findVariableAt', () => {
  it('命中 ${...} 范围内任意列', () => {
    const line = 'command: echo ${env.APP_ENV} done'
    const start = line.indexOf('${')
    expect(findVariableAt(line, start)).toEqual({
      expression: '${env.APP_ENV}',
      from: start,
      to: start + '${env.APP_ENV}'.length,
    })
    expect(findVariableAt(line, start + 3)?.expression).toBe('${env.APP_ENV}')
    // 末尾列（含右花括号）也算命中，便于鼠标贴边悬浮
    expect(findVariableAt(line, start + '${env.APP_ENV}'.length - 1)?.expression).toBe('${env.APP_ENV}')
  })

  it('不在变量范围时返回 null', () => {
    const line = 'command: echo ${env.APP_ENV} done'
    expect(findVariableAt(line, 0)).toBeNull()
    expect(findVariableAt('command: echo hello', 5)).toBeNull()
  })

  it('一行多个变量时返回光标命中的那个', () => {
    const line = 'echo ${env.A} ${env.B}'
    expect(findVariableAt(line, line.indexOf('${env.B}') + 1)?.expression).toBe('${env.B}')
  })
})

describe('resolveVariableInfo — env 作用域就近解析', () => {
  it('task.env 优先于 subpipeline/options/root', () => {
    const info = resolveVariableInfo('${env.APP_ENV}', index, {
      lineNumber: lineOf('echo ${env.APP_ENV} ${env.SUB_ONLY}'),
    })
    expect(info.kind).toBe('环境变量')
    expect(info.value).toBe('task-staging')
    expect(info.source).toContain('compile')
  })

  it('同 subpipeline 内无 task 覆盖时取 subpipeline config.env', () => {
    const info = resolveVariableInfo('${env.APP_ENV}', index, {
      lineNumber: lineOf('name: package'),
    })
    // package 任务没有 env，取 build 子流水线配置
    expect(info.value).toBe('sub-staging')
    expect(info.source).toContain('build')
  })

  it('subpipeline 未定义时回退 options.env / 顶层 env', () => {
    expect(resolveVariableInfo('${env.SUB_ONLY}', index).value).toBe('sub-value')
    expect(resolveVariableInfo('${env.ROOT_ONLY}', index).value).toBe('root-value')
  })

  it('任何作用域都未定义时标注运行时注入', () => {
    const info = resolveVariableInfo('${env.UNDEFINED}', index, {
      lineNumber: lineOf('echo ${env.APP_ENV} ${env.SUB_ONLY}'),
    })
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('运行时')
  })
})

describe('resolveVariableInfo — params', () => {
  it('展示声明中的默认值', () => {
    const info = resolveVariableInfo('${params.VERSION_TAG}', index)
    expect(info.kind).toBe('参数')
    expect(info.value).toBe('v2.0.0')
  })

  it('无默认值时说明运行时传入', () => {
    const info = resolveVariableInfo('${params.NO_DEFAULT}', index)
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('运行时')
  })

  it('未声明时给出提示', () => {
    const info = resolveVariableInfo('${params.NOT_DECLARED}', index)
    expect(info.value).toBeUndefined()
    expect(info.description).toBeTruthy()
  })
})

describe('resolveVariableInfo — agent / credential（项目配置注入）', () => {
  const agents = new Map<string, AgentVariableSource>([
    ['builder', { agent_id: 'builder', host: '10.98.1.100', port: 22 }],
  ])
  const credentials = new Map<string, CredentialVariableSource>([
    ['docker-registry', { id: 'c1', name: 'docker-registry', type: 'username_password' }],
    ['c2', { id: 'c2', name: 'npm-publish', type: 'token' }],
  ])

  it('agent host/port 从项目配置解析', () => {
    const host = resolveVariableInfo('${agent:builder.host}', index, { agents })
    expect(host.kind).toBe('Agent 属性')
    expect(host.value).toBe('10.98.1.100')
    const port = resolveVariableInfo('${agent:builder.port}', index, { agents })
    expect(port.value).toBe('22')
  })

  it('agent 不存在时说明未找到', () => {
    const info = resolveVariableInfo('${agent:missing.host}', index, { agents })
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('missing')
  })

  it('凭据只说明已配置，不回传内容', () => {
    const info = resolveVariableInfo('${credential:docker-registry}', index, { credentials })
    expect(info.kind).toBe('凭证')
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('不回传')
  })

  it('非管理员时提示权限不足而不是误报未找到', () => {
    const info = resolveVariableInfo('${credential:docker-registry}', index, {
      credentialsUnavailable: true,
    })
    expect(info.description).toContain('管理员')
  })
})

describe('resolveVariableInfo — 运行时变量与通用路径', () => {
  it('内置变量标注运行时可用', () => {
    const info = resolveVariableInfo('${PIPELINE_ID}', index)
    expect(info.kind).toBe('内置变量')
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('运行时')
  })

  it('上游任务输出 / 制品引用标注运行时', () => {
    expect(resolveVariableInfo('${task.compile.output}', index).kind).toBe('上游任务输出')
    expect(resolveVariableInfo('${artifact:dist/app.tar.gz}', index).kind).toBe('制品引用')
  })

  it('通用 dot-path 未定义时明确说明', () => {
    const info = resolveVariableInfo('${config.execution_strategy}', index)
    expect(info.kind).toBe('变量')
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('运行时')
  })
})

describe('buildVariableIndex — 非法 YAML 降级', () => {
  it('解析失败不抛错，env 走运行时说明', () => {
    const bad = buildVariableIndex('name: [unclosed')
    const info = resolveVariableInfo('${env.FOO}', bad)
    expect(info.kind).toBe('环境变量')
    expect(info.value).toBeUndefined()
    expect(info.description).toContain('运行时')
  })
})
