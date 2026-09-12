import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import YamlEditor from '../YamlEditor'
import { buildVariableIndex, buildVariableTooltipDom, resolveVariableInfo } from '@/utils/yamlVariables'

/**
 * YamlEditor 变量悬浮单测（2026-09）。
 *
 * CodeMirror 的 hover 触发依赖真实布局测量，jsdom 下不可靠；
 * 这里直接测试 tooltip 的 DOM 构造契约 + 带 variableHover 的渲染冒烟，
 * 解析逻辑本身由 yamlVariables.test.ts 覆盖。
 */
describe('buildVariableTooltipDom', () => {
  it('展示表达式、类型、来源与解析值', () => {
    const yaml = `name: t
pipelines:
  - name: build
    tasks:
      - name: compile
        env:
          FOO: bar
`
    const index = buildVariableIndex(yaml)
    const info = resolveVariableInfo('${env.FOO}', index, { lineNumber: 7 })
    const dom = buildVariableTooltipDom(info)
    expect(dom.textContent).toContain('${env.FOO}')
    expect(dom.textContent).toContain('环境变量')
    expect(dom.textContent).toContain('来源：task.compile.env')
    expect(dom.textContent).toContain('值：bar')
  })

  it('无静态值时展示运行时说明，不使用假值兜底', () => {
    const index = buildVariableIndex('name: t\n')
    const info = resolveVariableInfo('${env.MISSING}', index)
    const dom = buildVariableTooltipDom(info)
    expect(dom.textContent).toContain('运行时')
    expect(dom.textContent).not.toContain('值：')
  })
})

describe('YamlEditor 变量悬浮渲染', () => {
  it('传入 variableHover 时编辑器正常渲染', () => {
    const { container } = render(
      <YamlEditor
        value="name: t"
        onChange={() => {}}
        variableHover={{ index: buildVariableIndex('name: t\n') }}
      />,
    )
    expect(container.querySelector('.cm-editor')).toBeTruthy()
  })
})
