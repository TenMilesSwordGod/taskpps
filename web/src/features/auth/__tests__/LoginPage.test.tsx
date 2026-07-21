/**
 * issue #204 登录/注册页交互测试（TC-W171 ~ TC-W177）。
 *
 * 覆盖维度：交互 — Tab 切换 / 表单提交 / 校验 / 错误提示 / redirect 跳转。
 * 必须 fireEvent 触发交互，不能只测渲染快照。
 *
 * 注意(2026-07): Ant Design Button 的 accessible name 在 jsdom 中可能含额外空白，
 * 改用 container.querySelector('button[type="submit"]') 定位提交按钮，更可靠。
 *
 * 注意(2026-07): Ant Design App.useApp().message 在 jsdom 中 portal 不稳定渲染，
 * mock App.useApp() 返回 mockMessage，将文本直接写入 DOM，便于 getByText 断言。
 *
 * 注意(2026-07): antd Tabs 同时渲染两个 tab 的内容（隐藏的 tab 带 .ant-tabs-tabpane-hidden），
 * getSubmitButton 按 text 参数区分登录/注册按钮，避免误点隐藏 tab 的提交按钮。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import type { ReactNode } from 'react'

// ---------- Mocks ----------
// 控制 useLogin / useRegister 的行为
const mockLoginMutate = vi.fn()
const mockRegisterMutate = vi.fn()
const mockLoginIsPending = vi.fn(() => false)
const mockRegisterIsPending = vi.fn(() => false)

vi.mock('@/api/auth', () => ({
  useLogin: () => ({
    mutateAsync: mockLoginMutate,
    isPending: mockLoginIsPending(),
  }),
  useRegister: () => ({
    mutateAsync: mockRegisterMutate,
    isPending: mockRegisterIsPending(),
  }),
  setToken: vi.fn(),
  getToken: vi.fn(() => null),
  clearToken: vi.fn(),
}))

// mock navigate 和 searchParams
const mockNavigate = vi.fn()
const mockSearchParams = new URLSearchParams()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [mockSearchParams, vi.fn()],
  }
})

// mock antd App.useApp() 的 message：将文本直接 append 到 body，便于 jsdom 断言
// 设计决策：Ant Design App.useApp().message 在 jsdom 中 portal 不渲染，
// 改用 mock 把 message 文本写入 DOM，使 getByText 可定位
const mockMessage = {
  success: vi.fn((text: string) => appendMessage(text)),
  error: vi.fn((text: string) => appendMessage(text)),
  info: vi.fn((text: string) => appendMessage(text)),
  warning: vi.fn((text: string) => appendMessage(text)),
  loading: vi.fn(),
  destroy: vi.fn(),
}

function appendMessage(text: string) {
  const div = document.createElement('div')
  div.className = 'ant-message-notice-content'
  div.textContent = text
  document.body.appendChild(div)
}

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd')
  // 设计决策：App 是 React 组件不能 spread 覆盖，用 Object.assign 在原组件上替换 useApp
  // 否则 Wrapper 渲染 App 时会报 "Element type is invalid: got object"
  const AppComponent = actual.App as unknown as React.FC & { useApp: () => unknown }
  AppComponent.useApp = () => ({
    message: mockMessage,
    notification: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
    modal: { confirm: vi.fn(), info: vi.fn(), warning: vi.fn(), error: vi.fn() },
  })
  return { ...actual, App: AppComponent }
})

// ---------- Wrapper ----------
function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return (
    <QueryClientProvider client={qc}>
      <AntdApp>{children}</AntdApp>
    </QueryClientProvider>
  )
}

// 辅助: 等待 message 文本出现（mock message 已将文本写入 DOM）
async function waitForMessage(text: string) {
  await waitFor(() => {
    expect(screen.getByText(text)).toBeInTheDocument()
  })
}

// 辅助: 获取当前激活 Tab 中的提交按钮
// 设计决策：antd Tabs 同时渲染所有 tab 但隐藏非激活的，按 text 区分登录/注册按钮
function getSubmitButton(container: HTMLElement, text?: string): HTMLElement {
  const buttons = container.querySelectorAll('button[type="submit"]')
  if (text) {
    // 优先匹配文本内容的按钮
    for (const btn of Array.from(buttons)) {
      if (btn.textContent?.includes(text)) return btn as HTMLElement
    }
  }
  // 兜底：返回非隐藏 tab 中的按钮
  for (const btn of Array.from(buttons)) {
    const hidden = (btn as HTMLElement).closest('.ant-tabs-tabpane-hidden')
    if (!hidden) return btn as HTMLElement
  }
  return buttons[0] as HTMLElement
}

// 由于动态 import，需要在每个 it 内 import LoginPage
async function renderLogin() {
  const LoginPage = (await import('@/pages/LoginPage')).default
  const { container } = render(
    <Wrapper>
      <LoginPage />
    </Wrapper>,
  )
  return { container }
}

describe('LoginPage (issue #204)', () => {
  beforeEach(() => {
    mockLoginMutate.mockReset()
    mockRegisterMutate.mockReset()
    mockLoginIsPending.mockReturnValue(false)
    mockRegisterIsPending.mockReturnValue(false)
    mockNavigate.mockReset()
    mockSearchParams.delete('redirect')
    localStorage.clear()
    vi.clearAllMocks()
    // 清理 message DOM 残留
    document.body.querySelectorAll('.ant-message-notice-content').forEach((el) => el.remove())
  })

  it('TC-W171: Tab 切换登录/注册', async () => {
    const { container } = await renderLogin()
    // 初始是登录 tab，显示密码字段但无昵称字段
    expect(screen.getByPlaceholderText('请输入密码')).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('显示给他人的名字')).not.toBeInTheDocument()
    // 点击「注册」tab（Tab label 文本可被 getByText 定位）
    fireEvent.click(screen.getByText('注册'))
    // 应出现昵称字段
    await waitFor(() => {
      expect(screen.getByPlaceholderText('显示给他人的名字')).toBeInTheDocument()
    })
  })

  it('TC-W172: 登录表单提交成功跳转 dashboard', async () => {
    mockLoginMutate.mockResolvedValueOnce({ access_token: 'tok123', user: { id: 1 } })
    const { container } = await renderLogin()
    // 填表单
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'pass123' } })
    // 提交（按文本'登录'定位按钮，避免误点隐藏 tab 的注册按钮）
    fireEvent.click(getSubmitButton(container, '登录'))
    await waitFor(() => {
      expect(mockLoginMutate).toHaveBeenCalledWith({ username: 'alice', password: 'pass123' })
    })
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true })
    })
  })

  it('TC-W173: 注册成功切登录 Tab 并预填用户名', async () => {
    mockRegisterMutate.mockResolvedValueOnce({ id: 1 })
    const { container } = await renderLogin()
    // 切到注册 tab
    fireEvent.click(screen.getByText('注册'))
    await waitFor(() => {
      expect(screen.getByPlaceholderText('显示给他人的名字')).toBeInTheDocument()
    })
    // 填注册表单
    fireEvent.change(screen.getByPlaceholderText('字母/数字/下划线，3-32 位'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByPlaceholderText('显示给他人的名字'), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByPlaceholderText('至少 6 位'), { target: { value: 'pass123' } })
    // 提交注册表单（按文本'注册'定位按钮）
    fireEvent.click(getSubmitButton(container, '注册'))
    await waitFor(() => {
      expect(mockRegisterMutate).toHaveBeenCalled()
    })
    // 应切回登录 tab（登录提示语重新出现）
    await waitFor(() => {
      expect(screen.getByText('登录以继续')).toBeInTheDocument()
    })
  })

  it('TC-W174: 表单空字段验证错误', async () => {
    const { container } = await renderLogin()
    // 直接点登录（不填字段）
    fireEvent.click(getSubmitButton(container, '登录'))
    // 应出现校验提示
    await waitFor(() => {
      expect(screen.getByText('请输入用户名')).toBeInTheDocument()
    })
    expect(screen.getByText('请输入密码')).toBeInTheDocument()
    // 不应调用 mutate
    expect(mockLoginMutate).not.toHaveBeenCalled()
  })

  it('TC-W175: 登录失败 401 显示「用户名或密码错误」', async () => {
    // mock reject 401
    const err = Object.assign(new Error('fail'), { response: { status: 401, data: { detail: '用户名或密码错误' } } })
    mockLoginMutate.mockRejectedValueOnce(err)
    const { container } = await renderLogin()
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'alice' } })
    // 注意(2026-07): 密码长度需 >=6 满足 Form rule min:6，否则校验失败 onFinish 不触发
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'wrong123' } })
    fireEvent.click(getSubmitButton(container, '登录'))
    await waitForMessage('用户名或密码错误')
  })

  it('TC-W176: 注册冲突 409 显示「该用户名已被注册」', async () => {
    const err = Object.assign(new Error('fail'), { response: { status: 409, data: { detail: '该用户名已被注册' } } })
    mockRegisterMutate.mockRejectedValueOnce(err)
    const { container } = await renderLogin()
    fireEvent.click(screen.getByText('注册'))
    await waitFor(() => expect(screen.getByPlaceholderText('显示给他人的名字')).toBeInTheDocument())
    fireEvent.change(screen.getByPlaceholderText('字母/数字/下划线，3-32 位'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByPlaceholderText('显示给他人的名字'), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByPlaceholderText('至少 6 位'), { target: { value: 'pass123' } })
    fireEvent.click(getSubmitButton(container, '注册'))
    await waitForMessage('该用户名已被注册')
  })

  it('TC-Wxxx: 登录表单存在「30天不用免登录」复选框', async () => {
    const { container } = await renderLogin()
    // 复选框应存在于登录表单中
    const checkbox = screen.getByText('30天不用免登录')
    expect(checkbox).toBeInTheDocument()
    // 获取实际的 checkbox input（前一个兄弟元素或父元素内的 input[type="checkbox"]）
    const checkboxInput = container.querySelector('.ant-checkbox-input') as HTMLInputElement
    expect(checkboxInput).not.toBeNull()
    // 默认应未勾选
    expect(checkboxInput?.checked).toBe(false)
  })

  it('TC-Wxxx: 勾选「30天不用免登录」后发送 remember_me=true', async () => {
    mockLoginMutate.mockResolvedValueOnce({ access_token: 'tok123', user: { id: 1 } })
    const { container } = await renderLogin()
    // 填表单
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'pass123' } })
    // 勾选 remember_me 复选框
    const checkboxInput = container.querySelector('.ant-checkbox-input') as HTMLInputElement
    fireEvent.click(checkboxInput)
    expect(checkboxInput?.checked).toBe(true)
    // 提交
    fireEvent.click(getSubmitButton(container, '登录'))
    await waitFor(() => {
      expect(mockLoginMutate).toHaveBeenCalledWith({ username: 'alice', password: 'pass123', remember_me: true })
    })
  })

  it('TC-W177: redirect 参数跳回原页面', async () => {
    mockSearchParams.set('redirect', '/pipelines')
    mockLoginMutate.mockResolvedValueOnce({ access_token: 'tok123', user: { id: 1 } })
    const { container } = await renderLogin()
    fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'alice' } })
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'pass123' } })
    fireEvent.click(getSubmitButton(container, '登录'))
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/pipelines', { replace: true })
    })
  })
})
