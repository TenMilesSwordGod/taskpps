/**
 * issue #204 axios 拦截器测试（TC-W186 ~ TC-W188）。
 *
 * 覆盖维度：交互 — 请求自动附加 Authorization / 401 清 token 跳 login / login 请求 401 防死循环。
 * 用 axios 自定义 adapter 捕获请求/控制响应，验证拦截器行为。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import axios, { type InternalAxiosRequestConfig } from 'axios'

// 测试目标: web/src/api/client.ts 的拦截器
// 由于 client.ts 在 import 时就创建 axios 实例并注册拦截器，
// 我们通过动态 import 获取该实例，再用 adapter 验证。

const TOKEN_KEY = 'taskpps_token'

describe('apiClient axios interceptors (issue #204)', () => {
  let originalLocation: Location

  beforeEach(() => {
    originalLocation = window.location
    localStorage.clear()
    // mock window.location.href setter（jsdom 不支持直接赋值跳转）
    // 用 defineProperty 劫持 href
    const hrefGetter = vi.fn(() => 'http://localhost/')
    const hrefSetter = vi.fn()
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, get href() { return hrefGetter() }, set href(v) { hrefSetter(v) } },
    })
    ;(window as unknown as { _hrefSetter: typeof hrefSetter })._hrefSetter = hrefSetter
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
    vi.resetModules()
  })

  it('TC-W186: 请求自动附加 Authorization: Bearer <token>', async () => {
    localStorage.setItem(TOKEN_KEY, 'mytoken123')
    // 动态 import 确保 client.ts 重新执行（拦截器重新注册）
    const { default: apiClient } = await import('@/api/client')
    // 用自定义 adapter 捕获请求配置
    let capturedConfig: InternalAxiosRequestConfig | null = null
    apiClient.defaults.adapter = (config) => {
      capturedConfig = config
      return Promise.resolve({ data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config })
    }
    await apiClient.get('/api/v1/auth/me')
    expect(capturedConfig).not.toBeNull()
    expect(capturedConfig!.headers.Authorization).toBe('Bearer mytoken123')
  })

  it('TC-W187: 401 响应清 token 并跳 /login', async () => {
    localStorage.setItem(TOKEN_KEY, 'willbecleared')
    const { default: apiClient } = await import('@/api/client')
    // 模拟 401 响应
    apiClient.defaults.adapter = (config) => {
      return Promise.reject({
        response: { status: 401, data: { detail: '未登录' } },
        config,
        message: 'Request failed',
      })
    }
    // 访问非 /login 页触发 401
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        pathname: '/pipelines',
        get href() { return 'http://localhost/pipelines' },
        set href(v) { (window as unknown as { _hrefSetter: (v: string) => void })._hrefSetter(v) },
      },
    })
    const hrefSetter = vi.fn()
    ;(window as unknown as { _hrefSetter: typeof hrefSetter })._hrefSetter = hrefSetter

    await expect(apiClient.get('/api/v1/auth/me')).rejects.toBeDefined()
    // token 应被清除
    await vi.waitFor(() => {
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    })
    // 应跳转 /login?redirect=/pipelines
    await vi.waitFor(() => {
      expect(hrefSetter).toHaveBeenCalledWith(expect.stringContaining('/login?redirect='))
    })
  })

  it('TC-W188: login 请求 401 不跳转防死循环', async () => {
    localStorage.setItem(TOKEN_KEY, 'tok')
    const { default: apiClient } = await import('@/api/client')
    apiClient.defaults.adapter = (config) => {
      return Promise.reject({
        response: { status: 401, data: { detail: '用户名或密码错误' } },
        config,
        message: 'fail',
      })
    }
    const hrefSetter = vi.fn()
    ;(window as unknown as { _hrefSetter: typeof hrefSetter })._hrefSetter = hrefSetter

    // /api/v1/auth/login 的 401 不应触发跳转
    await expect(apiClient.post('/api/v1/auth/login', { username: 'x', password: 'y' })).rejects.toBeDefined()
    // 给一点时间确保不会有延迟跳转
    await new Promise((r) => setTimeout(r, 50))
    expect(hrefSetter).not.toHaveBeenCalled()
  })
})
