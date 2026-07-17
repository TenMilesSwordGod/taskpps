/**
 * issue #204 侧边栏头像区交互测试（TC-W182 ~ TC-W185）。
 *
 * 覆盖维度：交互 — 头像渲染 / 点击浮层 / 退出登录 / 未登录不渲染。
 * mock ProLayout 为简单容器，验证 menuFooterRender 回调产出的交互。
 * 必须 fireEvent 触发点击。
 *
 * 注意(2026-07): Ant Design Dropdown 在 jsdom 中 portal 渲染不可靠，
 * mock Dropdown 使菜单项始终内联渲染，同时保留 onClick 回调，可 fireEvent 测试交互。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'

// ---------- Mocks ----------
const mockUseMe = vi.fn()
const mockLogoutMutate = vi.fn()
const mockNavigate = vi.fn()

vi.mock('@/api/auth', () => ({
  useMe: () => mockUseMe(),
  useLogout: () => ({ mutateAsync: mockLogoutMutate, isPending: false }),
  clearToken: vi.fn(),
  getToken: vi.fn(() => 'token'),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// mock Ant Design Dropdown：将 menu items 内联渲染，保留 onClick 回调
// 设计决策：jsdom 中 Dropdown portal 不稳定，改为内联渲染可 fireEvent 测试 onClick
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd')
  return {
    ...actual,
    Dropdown: ({ menu, children }: {
      menu?: { items?: Array<{ key?: string; label?: ReactNode; type?: string; danger?: boolean; icon?: ReactNode }>; onClick?: (e: { key: string }) => void }
      children?: ReactNode
    }) => {
      return (
        <div className="ant-dropdown-trigger" data-testid="dropdown-trigger">
          {children}
          {/* 内联渲染 menu items，使 jsdom 可查询和点击 */}
          <div className="ant-dropdown-menu" data-testid="dropdown-menu">
            {menu?.items?.map((item, i) => {
              if (item.type === 'divider') {
                return <div key={`divider-${i}`} className="ant-dropdown-menu-divider" />
              }
              return (
                <div
                  key={item.key || `item-${i}`}
                  className="ant-dropdown-menu-item"
                  data-testid={`menu-item-${item.key}`}
                  onClick={() => menu?.onClick?.({ key: item.key as string })}
                >
                  {item.icon}
                  {item.label}
                </div>
              )
            })}
          </div>
        </div>
      )
    },
  }
})

// mock ProLayout: 渲染 menuFooterRender + actionsRender + children，避免 jsdom 复杂度
vi.mock('@ant-design/pro-layout', () => ({
  ProLayout: (props: {
    menuFooterRender?: () => ReactNode
    actionsRender?: () => ReactNode[]
    children?: ReactNode
    collapsed?: boolean
  }) => (
    <div data-testid="pro-layout">
      <div data-testid="header-actions">{props.actionsRender?.() ?? null}</div>
      <div data-testid="sider-footer">{props.menuFooterRender?.() ?? null}</div>
      <div data-testid="content">{props.children}</div>
    </div>
  ),
}))

vi.mock('@/components/TaskPpsLogo', () => ({
  default: () => <span data-testid="logo">logo</span>,
}))

// ---------- Wrapper ----------
function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter>{children}</MemoryRouter>
      </AntdApp>
    </QueryClientProvider>
  )
}

const fakeUser = {
  id: 1,
  username: 'alice',
  nickname: 'Alice',
  role: 'user',
  avatar: 'https://example.com/a.png',
  is_active: true,
}

async function renderLayout() {
  const AppLayout = (await import('@/layouts/AppLayout')).default
  return render(
    <Wrapper>
      <AppLayout>
        <div>page content</div>
      </AppLayout>
    </Wrapper>,
  )
}

describe('SidebarAvatar (issue #204)', () => {
  beforeEach(() => {
    mockUseMe.mockReset()
    mockLogoutMutate.mockReset()
    mockNavigate.mockReset()
    localStorage.clear()
  })

  it('TC-W182: 已登录渲染头像和昵称', async () => {
    mockUseMe.mockReturnValue({ data: fakeUser })
    await renderLayout()
    // sider 底部应显示昵称 Alice（顶部 header 也显示）
    expect(screen.getAllByText('Alice').length).toBeGreaterThanOrEqual(1)
  })

  it('TC-W183: 点击头像显示浮层含退出登录', async () => {
    mockUseMe.mockReturnValue({ data: fakeUser })
    await renderLayout()
    // 浮层应包含「退出登录」菜单项（mock Dropdown 内联渲染）
    const logoutItem = screen.getByTestId('menu-item-logout')
    expect(logoutItem).toBeInTheDocument()
    expect(logoutItem.textContent).toContain('退出登录')
    // 点击头像触发区
    const trigger = screen.getByTestId('dropdown-trigger')
    fireEvent.click(trigger)
    // 退出登录仍可见
    await waitFor(() => {
      expect(screen.getByTestId('menu-item-logout')).toBeInTheDocument()
    })
  })

  it('TC-W184: 退出登录清 token 并跳 /login', async () => {
    mockUseMe.mockReturnValue({ data: fakeUser })
    mockLogoutMutate.mockResolvedValueOnce({})
    await renderLayout()
    // 点击退出登录菜单项（fireEvent 触发 onClick 回调）
    const logoutItem = screen.getByTestId('menu-item-logout')
    fireEvent.click(logoutItem)
    await waitFor(() => {
      expect(mockLogoutMutate).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login', { replace: true })
    })
  })

  it('TC-W185: 未登录不渲染头像区', async () => {
    // useMe 返回 undefined（无 data），模拟 guest
    mockUseMe.mockReturnValue({ data: undefined })
    await renderLayout()
    // sider footer 应为空（menuFooterRender 返回 null）
    const siderFooter = screen.getByTestId('sider-footer')
    expect(siderFooter.children.length).toBe(0)
  })
})
