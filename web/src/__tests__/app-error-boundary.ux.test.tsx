/**
 * 全局错误边界 UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：错误边界（整页级）。
 * 背景：App 使用 `useRoutes`（非 data router），全仓库没有 ErrorBoundary/errorElement，
 * 任一页面渲染异常（如历史 bug38 的 nickname 崩溃）或懒加载 chunk 加载失败都会整页白屏，
 * 用户无提示、无法恢复。此文件以「页面抛错后应出现兜底提示」为验收条件，
 * `it.fails` 表示当前尚未实现（修复后改回 it）。
 * v2 (2026-09, issue #213): ErrorBoundary 已实现并接入 App，用例已转为常规断言。
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'

vi.mock('@/layouts/AppLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="app-layout">{children}</div>,
}))

// 模拟某业务页面在渲染期抛出异常（真实场景：后端字段缺失、第三方组件崩）
vi.mock('@/features/dashboard/DashboardPage', () => ({
  default: () => {
    throw new Error('boom: unexpected render error')
  },
}))

vi.mock('@/api/client', () => ({
  getToken: () => 'token',
  setToken: vi.fn(),
  clearToken: vi.fn(),
  default: { get: vi.fn(), post: vi.fn() },
}))

const App = (await import('@/App')).default

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={['/dashboard']}>{children}</MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

describe('全局错误边界 UX', () => {
  it('UX-页面渲染异常时展示全局兜底提示，而不是整页白屏', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <Wrapper>
          <App />
        </Wrapper>,
      )
    } catch {
      // 未实现错误边界时异常会向上冒泡；仍继续断言兜底 UI 是否存在
    }

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(await screen.findByText(/页面出错了|出错了|系统异常/)).toBeInTheDocument()
    consoleError.mockRestore()
  })

  it('UX-全局兜底提供「重新加载」恢复入口', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <Wrapper>
          <App />
        </Wrapper>,
      )
    } catch {
      // 同上
    }

    expect(await screen.findByRole('button', { name: /重新加载|刷新页面/ })).toBeInTheDocument()
    consoleError.mockRestore()
  })
})
