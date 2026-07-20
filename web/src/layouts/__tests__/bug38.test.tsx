import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'
import AppLayout from '@/layouts/AppLayout'

/**
 * Bug #38 RED 测试：[web] AppLayout user.nickname 为空/undefined 时整个页面白屏。
 *
 * 崩溃点分析：UserMenuFooter（AppLayout.tsx:142）
 *   {user.nickname.charAt(0).toUpperCase()}
 * 当 user.nickname 为 undefined / null 时，访问 .charAt 抛 TypeError，
 * React 渲染阶段崩溃 → 整页白屏（即使 nickname 字段类型声明为 string，
 * 后端 /me 实际可能缺失该字段）。
 * 注意：空字符串 '' 不会在 charAt 处崩溃（''.charAt(0) === ''），
 * 因此白屏的真实触发条件是 undefined / null；本测试针对这两类确定性复现。
 *
 * 本测试为 RED 阶段：断言「nickname 为 undefined/null 时页面内容可见」，
 * 修复前必然失败（渲染崩溃，body 为空 = 白屏）。
 */

// ---------- Mocks（复用 SidebarAvatar 测试的最小 mock 集）----------
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

// jsdom 中 Dropdown portal 不可靠，mock 为内联渲染以便组件可渲染
vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd')
  return {
    ...actual,
    Dropdown: ({ menu, children }: {
      menu?: { items?: Array<{ key?: string; label?: ReactNode; type?: string }> }
      children?: ReactNode
    }) => (
      <div className="ant-dropdown-trigger">
        {children}
        <div className="ant-dropdown-menu">
          {menu?.items?.map((item, i) => (
            <div key={item.key || `item-${i}`}>{item.label}</div>
          ))}
        </div>
      </div>
    ),
  }
})

// mock ProLayout 为简单容器，直接渲染 menuFooterRender 产出的 UserMenuFooter
vi.mock('@ant-design/pro-layout', () => ({
  ProLayout: (props: {
    menuFooterRender?: () => ReactNode
    children?: ReactNode
  }) => (
    <div data-testid="pro-layout">
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

const baseUser = {
  id: 1,
  username: 'alice',
  nickname: 'Alice',
  role: 'user',
  avatar: 'https://example.com/a.png',
  is_active: true,
}

function renderWithUser(user: unknown) {
  mockUseMe.mockReturnValue({ data: user })
  return render(
    <Wrapper>
      <AppLayout>
        <div>page content</div>
      </AppLayout>
    </Wrapper>,
  )
}

describe('Bug#38 — AppLayout user.nickname 为空/undefined 不应白屏', () => {
  beforeEach(() => {
    mockUseMe.mockReset()
    mockLogoutMutate.mockReset()
    mockNavigate.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
  })

  it('RED: nickname=undefined 时页面内容应可见（当前崩溃白屏，断言失败）', () => {
    const user = { ...baseUser, nickname: undefined }
    // 修复前：UserMenuFooter 调用 user.nickname.charAt(0) 抛 TypeError，
    // 整棵 React 树崩溃卸载 → body 为空（白屏），page content 不存在。
    // 修复后应通过（不抛错且正常渲染）。
    renderWithUser(user)
    expect(screen.queryByText('page content')).toBeInTheDocument()
  })

  it('RED: nickname=null 时页面内容应可见（当前崩溃白屏，断言失败）', () => {
    const user = { ...baseUser, nickname: null as unknown as string }
    renderWithUser(user)
    expect(screen.queryByText('page content')).toBeInTheDocument()
  })

  it('反向用例: nickname 正常时不白屏（防回归基线，应始终通过）', () => {
    const user = { ...baseUser, nickname: 'Alice' }
    renderWithUser(user)
    expect(screen.queryByText('page content')).toBeInTheDocument()
    expect(screen.getAllByText('Alice').length).toBeGreaterThanOrEqual(1)
  })
})
