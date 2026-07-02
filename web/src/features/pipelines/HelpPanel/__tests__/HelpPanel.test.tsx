import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import HelpPanel from '../HelpPanel'

vi.mock('../examplePipeline.yaml?raw', () => ({
  default: `version: "1.0"
name: test-pipeline

params:
  - name: DEPLOY_ENV
    label: 部署环境
    type: select
    default: staging

env:
  REGISTRY: "\${credential:docker-registry}"

pipelines:
  - name: build
    stage: build
    config:
      execution_strategy: parallel
    depends_on: []
    tasks:
      - name: compile
        command: echo "Building \${params.VERSION_TAG} on \${env.CI_BRANCH}"
        timeout: 300
        retry: 2
        env:
          NODE_ENV: production
          API_URL: "\${credential:api-key}"

      - name: test
        commands:
          - echo "Running tests..."
          - npm test
        when: \${env.ENABLE_TEST}
        on_failure: ignore

      - name: deploy
        depends_on:
          - compile
          - test
        invoke:
          task: deploy
          args:
            - "\${params.DEPLOY_ENV}"
        host: "\${agent:prod.host}"
        credential: "\${credential:ssh-key}"
`,
}))

describe('HelpPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('展开状态下渲染面板', () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('help-panel-expanded')).toBeInTheDocument()
    expect(screen.getByText('示例 Pipeline')).toBeInTheDocument()
    expect(screen.getByText('变量参考')).toBeInTheDocument()
  })

  it('最小化状态显示图标条', () => {
    render(
      <HelpPanel
        minimized={true}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('help-panel-minimized')).toBeInTheDocument()
  })

  it('点击展开按钮触发 onToggleMinimized', async () => {
    const toggle = vi.fn()
    render(
      <HelpPanel
        minimized={true}
        onToggleMinimized={toggle}
      />,
    )
    const btn = screen.getByTestId('help-panel-minimized')
    fireEvent.click(btn)
    expect(toggle).toHaveBeenCalled()
  })

  it('点击最小化按钮触发 onToggleMinimized', async () => {
    const toggle = vi.fn()
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={toggle}
      />,
    )
    const btn = screen.getByTestId('help-panel-minimize-btn')
    fireEvent.click(btn)
    expect(toggle).toHaveBeenCalled()
  })

  it('默认显示示例 Pipeline tab', () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('切换到变量参考 tab 显示变量表格', async () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    const varTab = screen.getByText('变量参考')
    fireEvent.click(varTab)
    await waitFor(() => {
      expect(screen.getByTestId('variable-reference-content')).toBeInTheDocument()
    })
  })

  it('示例 Pipeline 内容区域不可编辑', () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    const content = screen.getByTestId('example-pipeline-content')
    const input = content.querySelector('input, textarea, [contenteditable]')
    expect(input).toBeNull()
  })
})

describe('ExamplePipelineView', () => {
  it('渲染 YAML 内容', () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByText(/name: test-pipeline/)).toBeInTheDocument()
    expect(screen.getByText(/version: "1.0"/)).toBeInTheDocument()
  })

  it('渲染关键字 high-level 结构（name, version, pipelines）', async () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    // 这些是 YAML 关键字段，应出现在内容中
    const content = screen.getByTestId('example-pipeline-content')
    expect(content.textContent).toContain('version')
    expect(content.textContent).toContain('name')
    expect(content.textContent).toContain('pipelines')
  })

  it('${...} 变量被包裹在 span.var-ref 中', () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    const varSpans = document.querySelectorAll('.var-ref')
    expect(varSpans.length).toBeGreaterThan(0)
  })
})

describe('VariableReference', () => {
  it('列出常见内置变量', async () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('变量参考'))
    await waitFor(() => {
      expect(screen.getByText('${PIPELINE_ID}')).toBeInTheDocument()
      expect(screen.getByText('${JOB_ID}')).toBeInTheDocument()
      expect(screen.getByText('${STEP_ID}')).toBeInTheDocument()
      expect(screen.getByText('${WORKSPACE}')).toBeInTheDocument()
    })
  })

  it('每个变量显示名称、类型、说明', async () => {
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('变量参考'))
    await waitFor(() => {
      expect(screen.getAllByText('名称').length).toBeGreaterThan(0)
      expect(screen.getAllByText('类型').length).toBeGreaterThan(0)
      expect(screen.getAllByText('说明').length).toBeGreaterThan(0)
    })
  })
})
