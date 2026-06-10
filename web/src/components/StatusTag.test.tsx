import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusTag from './StatusTag'

describe('<StatusTag />', () => {
  it('渲染中文标签', () => {
    render(<StatusTag status="running" />)
    expect(screen.getByText('运行中')).toBeInTheDocument()
  })

  it('success 状态显示成功', () => {
    render(<StatusTag status="success" />)
    expect(screen.getByText('成功')).toBeInTheDocument()
  })

  it('failed 状态显示失败', () => {
    render(<StatusTag status="failed" />)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('skipped 状态显示已跳过', () => {
    render(<StatusTag status="skipped" />)
    expect(screen.getByText('已跳过')).toBeInTheDocument()
  })
})
