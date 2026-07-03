import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import WhenNode from '../WhenNode'
import type { NodeProps } from '@xyflow/react'

vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
}))

function renderWhenNode(partial: Partial<NodeProps> = {}) {
  const props = {
    id: 'when-a-b',
    type: 'whenNode',
    data: {},
    selected: false,
    isConnectable: true,
    xPos: 0,
    yPos: 0,
    dragging: false,
    zIndex: 0,
    ...partial,
  } as NodeProps
  return render(<WhenNode {...props} />)
}

describe('WhenNode — Gateway 模式', () => {
  it('isGateway=true 时渲染 50x50 菱形且无文字', () => {
    renderWhenNode({ data: { isGateway: true, whenTargets: [] } })
    const gateway = screen.getByTestId('gateway-node')
    expect(gateway).toBeInTheDocument()
    expect(gateway.classList.contains('w-[50px]')).toBe(true)
    expect(gateway.classList.contains('h-[50px]')).toBe(true)
    expect(screen.queryByTestId('when-node-text')).not.toBeInTheDocument()
  })

  it('gateway 菱形内部显示 X（两条交叉白线）', () => {
    renderWhenNode({ data: { isGateway: true, whenTargets: [] } })
    const gateway = screen.getByTestId('gateway-node')
    const lines = gateway.querySelectorAll('line')
    expect(lines).toHaveLength(2)
  })

  it('isGateway=true 时不渲染普通 when-node', () => {
    renderWhenNode({ data: { isGateway: true, when: '${X}' } })
    expect(screen.queryByTestId('when-node')).not.toBeInTheDocument()
  })
})

describe('WhenNode — 菱形决策节点渲染（非 Gateway 模式）', () => {
  it('渲染 when 表达式摘要文本', () => {
    const when = '${RUN_SMOKE}'
    renderWhenNode({ data: { when } })
    expect(screen.getByTestId('when-node')).toBeInTheDocument()
    expect(screen.getByTestId('when-node-text')).toHaveTextContent(when)
  })

  it('长表达式只显示首个变量引用作为摘要', () => {
    const when = '${params.A} == "1" && ${params.B} == "2"'
    renderWhenNode({ data: { when } })
    expect(screen.getByTestId('when-node-text')).toHaveTextContent('${params.A}')
  })

  it('无变量引用时长文本按字符截断并带省略号', () => {
    const when = 'always_run_on_success'
    renderWhenNode({ data: { when } })
    expect(screen.getByTestId('when-node-text')).toHaveTextContent('always_run…')
  })

  it('摘要文本使用等宽字体、截断样式并被放大到 12px', () => {
    const when = '${params.A} == "1" && ${params.B} == "2"'
    renderWhenNode({ data: { when } })
    const text = screen.getByTestId('when-node-text')
    expect(text.classList.contains('font-mono')).toBe(true)
    expect(text.classList.contains('truncate')).toBe(true)
    expect(text.classList.contains('text-xs')).toBe(true)
  })

  it('菱形容器尺寸为 90x90', () => {
    renderWhenNode({ data: { when: '${env.X}' } })
    const node = screen.getByTestId('when-node')
    expect(node.classList.contains('w-[90px]')).toBe(true)
    expect(node.classList.contains('h-[90px]')).toBe(true)
  })

  it('鼠标悬停时 Tooltip 显示完整 when 表达式', async () => {
    const when = '${params.A} == "1" && ${params.B} == "2" && ${params.C} == "3"'
    renderWhenNode({ data: { when } })
    const text = screen.getByTestId('when-node-text')

    fireEvent.mouseEnter(text)
    await waitFor(() => {
      const tooltips = document.querySelectorAll('.ant-tooltip')
      expect(tooltips.length).toBeGreaterThan(0)
      const hasFullWhen = Array.from(tooltips).some((t) =>
        t.textContent?.includes(when),
      )
      expect(hasFullWhen).toBe(true)
    })
  })

  it('变量引用原样显示，不展开求值', () => {
    const when = '${env.X}'
    renderWhenNode({ data: { when } })
    expect(screen.getByTestId('when-node-text')).toHaveTextContent(when)
  })
})
