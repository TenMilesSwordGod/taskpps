import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRetrySSELogs } from './useRetrySSELogs'

/** 简易 EventSource 桩：jsdom 不实现 EventSource */
type Listener = (e: { data: string; type?: string }) => void
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners: Record<string, Listener[]> = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(type: string, cb: Listener) {
    (this.listeners[type] ||= []).push(cb)
  }
  close() {
    this.readyState = 2
  }
  emit(type: string, data: string) {
    for (const cb of this.listeners[type] ?? []) cb({ data, type })
  }
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  fail() {
    this.readyState = 2
    this.onerror?.()
  }
  done() {
    this.emit('done', '')
  }
}

beforeEach(() => {
  MockEventSource.instances = []
  // @ts-expect-error - 注入桩
  globalThis.EventSource = MockEventSource
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useRetrySSELogs()', () => {
  it('runId 或 retryId 为空时：不建立连接', () => {
    const { result: r1 } = renderHook(() => useRetrySSELogs(undefined, 'retry-1'))
    expect(MockEventSource.instances).toHaveLength(0)
    expect(r1.current.logs).toEqual([])

    const { result: r2 } = renderHook(() => useRetrySSELogs('run-1', undefined))
    expect(MockEventSource.instances).toHaveLength(0)
    expect(r2.current.logs).toEqual([])
  })

  it('runId + retryId 给定后：建立 EventSource 连接到重试日志端点', () => {
    renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toBe('/api/runs/run-1/retry/retry-1/logs?follow=true')
  })

  it('连接打开后：connected 为 true', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].open())
    expect(result.current.connected).toBe(true)
  })

  it('收到 "retry_log" 事件后：追加到 logs', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'hello world'))
    expect(result.current.logs).toHaveLength(1)
    expect(result.current.logs[0].content).toBe('hello world')
  })

  it('多行 retry_log 事件：按换行拆分', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'line1\nline2\n\nline3'))
    expect(result.current.logs).toHaveLength(4)
    expect(result.current.logs.map((l) => l.content)).toEqual(['line1', 'line2', '', 'line3'])
  })

  it('每条日志有全局唯一的 seq，严格递增', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'a'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'b'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'c'))
    const seqs = result.current.logs.map((l) => l.seq)
    expect(new Set(seqs).size).toBe(3)
    for (let i = 1; i < seqs.length; i++) {
      expect(seqs[i]).toBeGreaterThan(seqs[i - 1])
    }
  })

  it('done 事件：关闭连接，connected 为 false', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    const es = MockEventSource.instances[0]
    act(() => es.open())
    act(() => es.done())
    expect(result.current.connected).toBe(false)
    expect(es.readyState).toBe(2)
  })

  it('网络错误：关闭连接，清空日志', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    const es = MockEventSource.instances[0]
    act(() => es.open())
    act(() => es.emit('retry_log', 'some log'))
    expect(result.current.logs).toHaveLength(1)
    act(() => es.fail())
    expect(result.current.connected).toBe(false)
    expect(result.current.logs).toHaveLength(0)
  })

  it('clearLogs：清空已收集的日志', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'x'))
    expect(result.current.logs.length).toBeGreaterThan(0)
    act(() => result.current.clearLogs())
    expect(result.current.logs).toEqual([])
  })

  it('组件卸载：关闭 EventSource', () => {
    const { unmount } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    const es = MockEventSource.instances[0]
    unmount()
    expect(es.readyState).toBe(2)
  })

  it('retryId 变更时：建立新连接', () => {
    const { rerender } = renderHook(
      ({ retryId }) => useRetrySSELogs('run-1', retryId),
      { initialProps: { retryId: 'retry-1' } },
    )
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('retry-1')

    rerender({ retryId: 'retry-2' })
    // 新连接建立
    expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(2)
    const latest = MockEventSource.instances[MockEventSource.instances.length - 1]
    expect(latest.url).toContain('retry-2')
  })

  it('\\r 字符正确剥离', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].emit('retry_log', 'line1\r\nline2'))
    expect(result.current.logs).toHaveLength(2)
    expect(result.current.logs[0].content).toBe('line1')
    expect(result.current.logs[1].content).toBe('line2')
  })

  it('空字符串 SSE 事件：不追加任何日志', () => {
    const { result } = renderHook(() => useRetrySSELogs('run-1', 'retry-1'))
    act(() => MockEventSource.instances[0].emit('retry_log', ''))
    expect(result.current.logs).toHaveLength(0)
  })
})
