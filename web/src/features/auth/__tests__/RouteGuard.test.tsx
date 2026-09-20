/**
 * issue #204 路由守卫测试（TC-W178 ~ TC-W181）。
 *
 * 覆盖维度：交互 — 未登录跳 login / 根路径重定向 / dashboard 公开 / redirect 参数。
 *
 * v2 (2026-09, QA 审计)：旧实现自行复制了一份路由表 + 组件，测试的是「副本」而非真实
 * routes.tsx，且 createMemoryRouter 在 jsdom 下产生 AbortSignal unhandled rejection，
 * 导致 TC-W178/180 长期红。现改为渲染真实 <App />（useRoutes）+ MemoryRouter，
 * 仅 mock 页面组件与 token，保证测的是真实路由配置。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'

const mocks = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(() => null),
}))

vi.mock('@/api/client', () => ({
  getToken: () => mocks.getToken(),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  default: { get: vi.fn(), post: vi.fn() },
}))

// 页面组件 mock 为占位；LoginPage 额外暴露 redirect 查询参数供断言
vi.mock('@/features/dashboard/DashboardPage', () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>,
}))
vi.mock('@/features/pipelines/PipelineListPage', () => ({
  default: () => <div data-testid="pipelines-page">Pipelines</div>,
}))
vi.mock('@/pages/LoginPage', async () => {
  const React = await import('react')
  const { useLocation } = await import('react-router-dom')
  // 大驼峰命名，满足 react-hooks 规则识别为组件
  const LoginPageMock = () => {
    const loc = useLocation()
    return React.createElement(
      'div',
      { 'data-testid': 'login-page', 'data-search': loc.search },
      'Login',
    )
  }
  return { default: LoginPageMock }
})
vi.mock('@/layouts/AppLayout', () => ({
  default: ({ children }: { children: ReactNode }) => <div data-testid="app-layout">{children}</div>,
}))

const App = (await import('@/App')).default

function renderApp(initialEntries: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={initialEntries}>
          <App />
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>,
  )
}

describe('RouteGuard (issue #204)', () => {
  beforeEach(() => {
    mocks.getToken.mockReset()
    localStorage.clear()
  })

  it('TC-W178: 未登录访问受保护路由 /pipelines 跳 /login 且携带 redirect', async () => {
    mocks.getToken.mockReturnValue(null)
    renderApp(['/pipelines'])

    const login = await screen.findByTestId('login-page')
    expect(login.getAttribute('data-search')).toContain('redirect=%2Fpipelines')
    expect(screen.queryByTestId('pipelines-page')).not.toBeInTheDocument()
  })

  it('TC-W180: 根路径 / 重定向到 /dashboard', async () => {
    mocks.getToken.mockReturnValue(null)
    renderApp(['/'])
    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument()
  })

  it('TC-W181: dashboard 公开无需登录', async () => {
    mocks.getToken.mockReturnValue(null)
    renderApp(['/dashboard'])
    expect(await screen.findByTestId('dashboard-page')).toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })

  it('TC-W178b: 已登录访问 /pipelines 正常显示', async () => {
    mocks.getToken.mockReturnValue('valid-token')
    renderApp(['/pipelines'])
    expect(await screen.findByTestId('pipelines-page')).toBeInTheDocument()
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
  })
})
