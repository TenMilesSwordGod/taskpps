import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from '../LoginPage';

// antd message static 方法在 jsdom 中报错：mock 掉
vi.mock('antd', async () => {
  const actual = await vi.importActual('antd');
  return {
    ...(actual as object),
    App: Object.assign((actual as { App: object }).App, {
      useApp: () => ({ message: { success: vi.fn(), error: vi.fn() } }),
    }),
  };
});

// atan2 query hooks：mock 返回 idle 状态
vi.mock('@/api/auth', () => ({
  useLogin: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useRegister: () => ({ mutate: vi.fn(), isPending: false }),
}));

// v2 (2026-07): mock TaskPpsLogo — svg 渲染正常，不需要真实图表
vi.mock('@/components/TaskPpsLogo', () => ({
  default: () => <div data-testid="taskpps-logo">logo</div>,
}));

describe('LoginPage — 表单可访问性与文案', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderLoginPage() {
    return render(
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>,
    );
  }

  it('登录用户名输入框设置 autoComplete="username"', () => {
    renderLoginPage();
    const usernameInput = screen.getByPlaceholderText('请输入用户名');
    expect(usernameInput).toHaveAttribute('autocomplete', 'username');
  });

  it('密码输入框设置 autoComplete="current-password"', () => {
    renderLoginPage();
    const passwordInput = screen.getByPlaceholderText('请输入密码');
    expect(passwordInput).toHaveAttribute('autocomplete', 'current-password');
  });

  it('不阻止浏览器密码管理器（无 autoComplete="off"）', () => {
    renderLoginPage();
    const form = document.querySelector('form');
    expect(form?.getAttribute('autocomplete')).not.toBe('off');
  });

  it('"30天内免登录" 文案清晰明确', () => {
    renderLoginPage();
    expect(screen.getByText('30天内免登录')).toBeInTheDocument();
  });
});
