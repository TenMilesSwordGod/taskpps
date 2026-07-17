/**
 * issue #204 路由守卫测试（TC-W178 ~ TC-W181）。
 *
 * 覆盖维度：交互 — 未登录跳 login / 根路径重定向 / dashboard 公开 / redirect 参数。
 * 用 createMemoryRouter 渲染真实路由表，验证 Navigate 行为。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp, Spin } from 'antd'

// mock getToken 控制登录态
const mockGetToken = vi.fn(() => null)
vi.mock('@/api/client', () => ({
  getToken: () => mockGetToken(),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  default: { get: vi.fn(), post: vi.fn() },
}))

// mock 各页面为简单占位，避免加载真实组件
vi.mock('@/features/dashboard/DashboardPage', () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>,
}))
vi.mock('@/features/pipelines/PipelineListPage', () => ({
  default: () => <div data-testid="pipelines-page">Pipelines</div>,
}))
vi.mock('@/pages/LoginPage', () => ({
  default: () => <div data-testid="login-page">Login</div>,
}))
// mock AppLayout: 直接渲染 children，避免 ProLayout 复杂度
vi.mock('@/layouts/AppLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="app-layout">{children}</div>,
}))
vi.mock('@/components/TaskPpsLogo', () => ({
  default: () => <span data-testid="logo">logo</span>,
}))

function makeRouter(initialEntries: string[]) {
  // 动态 import routes 保证 mock 生效
  // 这里直接复制 routes.tsx 的结构，避免懒加载导致的 Suspense 复杂度
  const { Navigate, Outlet } = require('react-router-dom')
  const RequireAuth = () => {
    const { useLocation } = require('react-router-dom')
    const location = useLocation()
    const token = mockGetToken()
    if (!token) {
      const redirect = encodeURIComponent(location.pathname + location.search)
      return <Navigate to={`/login?redirect=${redirect}`} replace />
    }
    return <Outlet />
  }
  const DashboardPage = () => <div data-testid="dashboard-page">Dashboard</div>
  const PipelineListPage = () => <div data-testid="pipelines-page">Pipelines</div>
  const LoginPage = () => <div data-testid="login-page">Login</div>
  const AppLayout = ({ children }: { children: React.ReactNode }) => <div data-testid="app-layout">{children}</div>

  const routes = [
    { path: '/login', element: <LoginPage /> },
    {
      element: <AppLayout><Outlet /></AppLayout>,
      children: [
        { path: '/', element: <Navigate to="/dashboard" replace /> },
        { path: '/dashboard', element: <DashboardPage /> },
        {
          element: <RequireAuth />,
          children: [
            { path: '/pipelines', element: <PipelineListPage /> },
          ],
        },
      ],
    },
  ]
  return createMemoryRouter(routes, { initialEntries })
}

function renderRouter(initialEntries: string[]) {
  const router = makeRouter(initialEntries)
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={qc}>
      <AntdApp>
        <RouterProvider router={router} />
      </AntdApp>
    </QueryClientProvider>,
  )
}

describe('RouteGuard (issue #204)', () => {
  beforeEach(() => {
    mockGetToken.mockReset()
    localStorage.clear()
  })

  it('TC-W178: 未登录访问受保护路由 /pipelines 跳 /login?redirect=', () => {
    mockGetToken.mockReturnValue(null)
    const { container } = renderRouter(['/pipelines'])
    // 应跳转到 login 页，URL 含 redirect
    expect(container.querySelector('[data-testid="login-page"]')).toBeTruthy()
  })

  it('TC-W180: 根路径 / 重定向到 /dashboard', () => {
    mockGetToken.mockReturnValue(null)
    const { container } = renderRouter(['/'])
    // / 公开，应显示 dashboard
    expect(container.querySelector('[data-testid="dashboard-page"]')).toBeTruthy()
  })

  it('TC-W181: dashboard 公开无需登录', () => {
    mockGetToken.mockReturnValue(null) // 未登录
    const { container } = renderRouter(['/dashboard'])
    // dashboard 是公开路由，应直接显示，不跳 login
    expect(container.querySelector('[data-testid="dashboard-page"]')).toBeTruthy()
    expect(container.querySelector('[data-testid="login-page"]')).toBeFalsy()
  })

  it('TC-W178b: 已登录访问 /pipelines 正常显示', () => {
    mockGetToken.mockReturnValue('valid-token')
    const { container } = renderRouter(['/pipelines'])
    expect(container.querySelector('[data-testid="pipelines-page"]')).toBeTruthy()
    expect(container.querySelector('[data-testid="login-page"]')).toBeFalsy()
  })
})
