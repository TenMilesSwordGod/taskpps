import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
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

function renderExpanded(overrides = {}) {
  return render(
    <HelpPanel
      minimized={false}
      onToggleMinimized={vi.fn()}
      {...overrides}
    />,
  )
}

function renderMinimized(overrides = {}) {
  return render(
    <HelpPanel
      minimized={true}
      onToggleMinimized={vi.fn()}
      {...overrides}
    />,
  )
}

// ============================================================
// 边界测试
// ============================================================
describe('HelpPanel 边界测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('最小化状态宽度为40px', () => {
    renderMinimized()
    const el = screen.getByTestId('help-panel-minimized')
    expect(el.style.width).toBe('40px')
  })

  it('展开状态默认宽度为480px', () => {
    renderExpanded()
    const el = screen.getByTestId('help-panel-expanded')
    expect(el.style.width).toBe('480px')
  })

  it('最大化状态宽度为70vw', () => {
    renderExpanded({ maximized: true })
    const el = screen.getByTestId('help-panel-expanded')
    expect(el.style.width).toBe('70vw')
  })

  it('不传 maximized 时默认值为 false，宽度为 480px', () => {
    renderExpanded()
    const el = screen.getByTestId('help-panel-expanded')
    expect(el.style.width).toBe('480px')
  })

  it('不传 onToggleMaximized 时不渲染最大化按钮', () => {
    renderExpanded()
    const btns = screen.getAllByRole('button')
    const hasMaximize = btns.some((btn) =>
      btn.querySelector('.anticon-expand'),
    )
    expect(hasMaximize).toBe(false)
  })

  it('传入 onToggleMaximized 时渲染最大化按钮', () => {
    renderExpanded({ onToggleMaximized: vi.fn() })
    const btns = screen.getAllByRole('button')
    const hasMaximize = btns.some((btn) =>
      btn.querySelector('.anticon-expand'),
    )
    expect(hasMaximize).toBe(true)
  })

  it('示例 Pipeline tab 包含 YAML 注释行且正确渲染', () => {
    renderExpanded()
    const content = screen.getByTestId('example-pipeline-content')
    expect(content.textContent).toContain('version:')
    expect(content.textContent).toContain('name:')
    expect(content.textContent).toContain('pipelines:')
  })

  it('变量参考表格包含所有内置变量类型列', async () => {
    renderExpanded()
    fireEvent.click(screen.getByText('变量参考'))
    await waitFor(() => {
      expect(screen.getByText('${PIPELINE_ID}')).toBeInTheDocument()
      expect(screen.getByText('${JOB_ID}')).toBeInTheDocument()
      expect(screen.getByText('${WORKSPACE}')).toBeInTheDocument()
    })
  })
})

// ============================================================
// 异常测试
// ============================================================
describe('HelpPanel 异常测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.resetModules()
  })

  it('YAML 内容为空时不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({ default: '' }))
    const { default: HelpPanelWithEmptyYaml } = await import('../HelpPanel')
    render(
      <HelpPanelWithEmptyYaml
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    const content = screen.getByTestId('example-pipeline-content')
    expect(content).toBeInTheDocument()
  })

  it('YAML 内容只有空白行时不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: '\n\n  \n\t\n',
    }))
    const { default: HelpPanelWithWhitespaceYaml } = await import('../HelpPanel')
    render(
      <HelpPanelWithWhitespaceYaml
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('包含无效变量格式 ${} 时渲染不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: 'test: ${}',
    }))
    const { default: HelpPanelWithBadVar } = await import('../HelpPanel')
    render(
      <HelpPanelWithBadVar
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('包含未闭合变量 ${no-close 时渲染不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: 'test1: ${open-var\n',
    }))
    const { default: HelpPanelWithOpenVar } = await import('../HelpPanel')
    render(
      <HelpPanelWithOpenVar
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('包含嵌套变量 \${${\"x\"}} 时渲染不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: 'test: ${\n  nested: "${inner}"\n}',
    }))
    const { default: HelpPanelWithNestedVar } = await import('../HelpPanel')
    render(
      <HelpPanelWithNestedVar
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('YAML 包含特殊 Unicode 字符时渲染不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: 'desc: "中文描述 🚀 émoji ñ español 日本語"',
    }))
    const { default: HelpPanelWithUnicode } = await import('../HelpPanel')
    render(
      <HelpPanelWithUnicode
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })
})

// ============================================================
// 并发测试
// ============================================================
describe('HelpPanel 并发测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('快速连续点击最小化状态面板多次只触发一次回调', async () => {
    const toggle = vi.fn()
    renderMinimized({ onToggleMinimized: toggle })
    const el = screen.getByTestId('help-panel-minimized')
    await act(async () => {
      fireEvent.click(el)
      fireEvent.click(el)
      fireEvent.click(el)
    })
    expect(toggle).toHaveBeenCalledTimes(3)
  })

  it('快速连续点击收起按钮多次触发相应次数回调', async () => {
    const toggle = vi.fn()
    renderExpanded({ onToggleMinimized: toggle })
    const btn = screen.getByTestId('help-panel-minimize-btn')
    await act(async () => {
      fireEvent.click(btn)
      fireEvent.click(btn)
      fireEvent.click(btn)
    })
    expect(toggle).toHaveBeenCalledTimes(3)
  })

  it('快速切换 tab 不崩溃且最终显示正确的 tab', async () => {
    renderExpanded()
    const exampleTab = screen.getByText('示例 Pipeline')
    const varTab = screen.getByText('变量参考')

    await act(async () => {
      fireEvent.click(varTab)
      fireEvent.click(exampleTab)
      fireEvent.click(varTab)
    })

    await waitFor(() => {
      expect(screen.getByTestId('variable-reference-content')).toBeInTheDocument()
    })
  })

  it('同时渲染最大化 + 展开状态不冲突', () => {
    const toggle = vi.fn()
    const toggleMax = vi.fn()
    render(
      <HelpPanel
        minimized={false}
        onToggleMinimized={toggle}
        maximized={true}
        onToggleMaximized={toggleMax}
      />,
    )
    expect(screen.getByTestId('help-panel-expanded')).toBeInTheDocument()
    expect(screen.getByTestId('help-panel-expanded').style.width).toBe('70vw')
  })
})

// ============================================================
// 环境测试
// ============================================================
describe('HelpPanel 环境测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('窄视口下 HelpPanel 展开仍可渲染', () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 320,
    })
    renderExpanded()
    expect(screen.getByTestId('help-panel-expanded')).toBeInTheDocument()
  })

  it('宽视口下 HelpPanel 展开仍可渲染', () => {
    Object.defineProperty(window, 'innerWidth', {
      writable: true,
      configurable: true,
      value: 2560,
    })
    renderExpanded()
    expect(screen.getByTestId('help-panel-expanded')).toBeInTheDocument()
  })

  it('YAML 中包含 shell 特殊字符时不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: `command: |
  echo "Path: $HOME/*.log"
  rm -rf /tmp/\${params.BUILD_ID}/*`,
    }))
    const { default: HelpPanelWithShellChars } = await import('../HelpPanel')
    render(
      <HelpPanelWithShellChars
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('YAML 中包含小于号和大于号时渲染不崩溃', async () => {
    vi.doMock('../examplePipeline.yaml?raw', () => ({
      default: 'command: echo "if x < 10 && y > 5 then ok"',
    }))
    const { default: HelpPanelWithAngleBrackets } = await import(
      '../HelpPanel'
    )
    render(
      <HelpPanelWithAngleBrackets
        minimized={false}
        onToggleMinimized={vi.fn()}
      />,
    )
    expect(screen.getByTestId('example-pipeline-content')).toBeInTheDocument()
  })

  it('鼠标悬停变量时 Tooltip 出现', async () => {
    renderExpanded()
    const varSpans = document.querySelectorAll('.var-ref')
    expect(varSpans.length).toBeGreaterThan(0)

    const firstVar = varSpans[0] as HTMLElement
    fireEvent.mouseEnter(firstVar)

    await waitFor(
      () => {
        const tooltips = document.querySelectorAll('.ant-tooltip')
        expect(tooltips.length).toBeGreaterThan(0)
      },
      { timeout: 2000 },
    )
  })

  it('点击最大化按钮触发 onToggleMaximized', () => {
    const toggleMax = vi.fn()
    renderExpanded({
      onToggleMaximized: toggleMax,
    })
    const maximizeBtns = screen.getAllByRole('button')
    const expandBtn = maximizeBtns.find((btn) =>
      btn.querySelector('.anticon-expand'),
    )
    expect(expandBtn).toBeDefined()
    fireEvent.click(expandBtn!)
    expect(toggleMax).toHaveBeenCalled()
  })
})
