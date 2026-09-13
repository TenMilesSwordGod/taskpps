/**
 * LoginPage UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：提交防重反馈 / 网络异常文案。
 * 背景：现有用例覆盖 Tab 切换、401/409、空字段校验与 redirect；
 * 「请求进行中是否明确 loading」「网络层异常是否给出可理解的中文提示」无覆盖。
 *
 * `it.fails` = 已确认缺陷（Network Error 原样透出；修复后改回 it）。
 * v2 (2026-09, issue #222): 网络异常已映射为中文提示，用例已转为常规断言。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockLoginMutate = vi.fn()
const mockLoginIsPending = vi.fn(() => false)
const mockMessageError = vi.fn()
const mockMessageSuccess = vi.fn()

vi.mock('@/api/auth', () => ({
  useLogin: () => ({ mutateAsync: mockLoginMutate, isPending: mockLoginIsPending() }),
  useRegister: () => ({ mutateAsync: vi.fn(), isPending: false }),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  getToken: vi.fn(() => null),
}))

vi.mock('@/components/TaskPpsLogo', () => ({
  default: () => <div data-testid="taskpps-logo">logo</div>,
}))

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd')
  const AppComponent = actual.App as unknown as React.FC & { useApp: () => unknown }
  AppComponent.useApp = () => ({
    message: {
      success: mockMessageSuccess,
      error: mockMessageError,
      info: vi.fn(),
      warning: vi.fn(),
      loading: vi.fn(),
      destroy: vi.fn(),
    },
    modal: { confirm: vi.fn() },
    notification: { success: vi.fn(), error: vi.fn() },
  })
  return { ...actual, App: AppComponent }
})

const LoginPage = (await import('../LoginPage')).default

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <LoginPage />
    </MemoryRouter>,
  )
}

function fillLoginForm(container: HTMLElement) {
  fireEvent.change(screen.getByPlaceholderText('请输入用户名'), { target: { value: 'alice' } })
  fireEvent.change(screen.getByPlaceholderText('请输入密码'), { target: { value: 'pass123' } })
  return container
}

beforeEach(() => {
  mockLoginMutate.mockReset()
  mockLoginIsPending.mockReset()
  mockLoginIsPending.mockReturnValue(false)
  mockMessageError.mockReset()
  mockMessageSuccess.mockReset()
})

describe('LoginPage UX-提交防重反馈', () => {
  it('UX-登录请求进行中提交按钮进入 loading（阻止重复提交）', () => {
    mockLoginIsPending.mockReturnValue(true)
    const { container } = renderLoginPage()

    const submit = container.querySelector('button[type="submit"]') as HTMLButtonElement
    expect(submit.className).toContain('ant-btn-loading')
  })

  it('UX-登录请求进行中重复点击不会二次提交', () => {
    mockLoginIsPending.mockReturnValue(true)
    const { container } = renderLoginPage()
    fillLoginForm(container)

    const submit = container.querySelector('button[type="submit"]') as HTMLButtonElement
    fireEvent.click(submit)
    fireEvent.click(submit)

    expect(mockLoginMutate).not.toHaveBeenCalled()
  })
})

describe('LoginPage UX-网络异常文案', () => {
  it('UX-网络层异常时展示可理解的中文提示，而不是原始 "Network Error"', async () => {
    mockLoginMutate.mockRejectedValue(new Error('Network Error'))
    const { container } = renderLoginPage()
    fillLoginForm(container)

    fireEvent.click(container.querySelector('button[type="submit"]') as HTMLButtonElement)

    await waitFor(() => expect(mockMessageError).toHaveBeenCalled())
    const shown = String(mockMessageError.mock.calls[0]?.[0] ?? '')
    expect(shown).toMatch(/网络|连接|服务不可用|稍后重试/)
    expect(shown).not.toBe('Network Error')
  })
})
