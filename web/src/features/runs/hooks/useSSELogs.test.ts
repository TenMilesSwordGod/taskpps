import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSSELogs } from './useSSELogs'

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
  /** 触发自定义事件（仅测试用） */
  emit(type: string, data: string) {
    for (const cb of this.listeners[type] ?? []) cb({ data, type })
  }
  /** 模拟连接打开 */
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  /** 模拟网络错误 */
  fail() {
    this.readyState = 2
    this.onerror?.()
  }
  /** 模拟 done 事件 */
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

describe('useSSELogs()', () => {
  it('runId 为空时：不建立连接', () => {
    const { result } = renderHook(() => useSSELogs(undefined))
    expect(MockEventSource.instances).toHaveLength(0)
    expect(result.current.logs).toEqual([])
    expect(result.current.connected).toBe(false)
  })

  it('runId 给定后：建立 EventSource 并标记 connected', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toBe('/api/runs/run-1/logs?follow=true')
    act(() => MockEventSource.instances[0].open())
    expect(result.current.connected).toBe(true)
  })

  it('收到 "log" 事件后：按 "task: content" 拆分并追加到 logs', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    act(() => es.emit('log', 'build: hello world'))
    expect(result.current.logs).toHaveLength(1)
    expect(result.current.logs[0]).toMatchObject({ taskName: 'build', content: 'hello world' })
  })

  it('无 taskName 前缀：作为匿名日志', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'orphan line'))
    expect(result.current.logs[0].taskName).toBe('')
    expect(result.current.logs[0].content).toBe('orphan line')
  })

  it('单事件多行：按换行拆分并保留空行', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'build: line1\nline2\n\nline3'))
    expect(result.current.logs).toHaveLength(4)
    expect(result.current.logs.map((l) => l.content)).toEqual(['line1', 'line2', '', 'line3'])
    expect(result.current.logs.every((l) => l.taskName === 'build')).toBe(true)
  })

  it('每条日志有全局唯一的 seq，同毫秒内不重复（P0-5 回归）', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    // 模拟同一毫秒内 3 个 SSE 事件各推送 2 行
    act(() => MockEventSource.instances[0].emit('log', 'build: a\nbuild: b'))
    act(() => MockEventSource.instances[0].emit('log', 'test: c\ntest: d'))
    act(() => MockEventSource.instances[0].emit('log', 'deploy: e\ndeploy: f'))
    const seqs = result.current.logs.map((l) => l.seq)
    // 6 条日志，seq 全部唯一
    expect(new Set(seqs).size).toBe(6)
    // seq 严格递增
    for (let i = 1; i < seqs.length; i++) {
      expect(seqs[i]).toBeGreaterThan(seqs[i - 1])
    }
  })

  it('超过 MAX_LOG_LINES 上限：裁剪为 75%', async () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    // 单次事件推 50001 行：触发上限保护 (MAX_LOG_LINES=50000)
    const lines: string[] = []
    for (let i = 0; i < 50001; i++) lines.push(`build: line${i}`)
    act(() => es.emit('log', lines.join('\n')))
    // 裁剪后应不超过 50000 * 0.75 = 37500
    expect(result.current.logs.length).toBeLessThanOrEqual(37500)
    expect(result.current.logs.length).toBeGreaterThan(0)
  })

  it('done 事件：关闭连接并把 connected 置为 false', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    act(() => es.open())
    act(() => es.done())
    expect(result.current.connected).toBe(false)
    expect(es.readyState).toBe(2)
  })

  it('网络错误：同样关闭并断开', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    act(() => es.open())
    act(() => es.fail())
    expect(result.current.connected).toBe(false)
  })

  it('重连时清空已有日志，避免重复（Issue #66）', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    act(() => es.open())
    // 先积累一些日志
    act(() => es.emit('log', 'build: line1'))
    act(() => es.emit('log', 'build: line2'))
    expect(result.current.logs).toHaveLength(2)
    // 网络错误触发重连：日志应被清空，避免重连后服务端从 position 0 重发导致重复
    act(() => es.fail())
    expect(result.current.logs).toHaveLength(0)
  })

  it('clearLogs：清空已收集的日志', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'build: x'))
    expect(result.current.logs.length).toBeGreaterThan(0)
    act(() => result.current.clearLogs())
    expect(result.current.logs).toEqual([])
  })

  it('组件卸载：关闭 EventSource', () => {
    const { unmount } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    unmount()
    expect(es.readyState).toBe(2)
  })

  // ─── P0-5 边界条件：seq 跨生命周期 ───

  it('seq 跨 hook re-mount 保持递增（模块级计数器不重置）', () => {
    const { result: r1, unmount: u1 } = renderHook(() => useSSELogs('run-A'))
    act(() => MockEventSource.instances[0].emit('log', 'a: x'))
    const seqA = r1.current.logs[0].seq
    u1()

    // 第二个 run：seq 应从此前最后一个 seq + 1 开始
    const { result: r2 } = renderHook(() => useSSELogs('run-B'))
    act(() => MockEventSource.instances[1]!.emit('log', 'b: y'))
    expect(r2.current.logs[0].seq).toBeGreaterThan(seqA)
  })

  it('seq 在 clearLogs 后继续递增', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'a: x'))
    const seqBefore = result.current.logs[0].seq
    act(() => result.current.clearLogs())
    act(() => MockEventSource.instances[0].emit('log', 'a: y'))
    expect(result.current.logs[0].seq).toBeGreaterThan(seqBefore)
  })

  it('上限裁剪后 seq 保留（裁剪的是旧数据，新数据 seq 正确）', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    // 先推 5001 行触发裁剪
    const batch1: string[] = []
    for (let i = 0; i < 5001; i++) batch1.push(`build: pre${i}`)
    act(() => es.emit('log', batch1.join('\n')))
    const seqsAfterTrim = result.current.logs.map((l) => l.seq)

    // 再推 3 条新日志
    act(() => es.emit('log', 'deploy: a\ndeploy: b\ndeploy: c'))
    const newSeqs = result.current.logs.map((l) => l.seq)

    // 新日志的 seq 大于裁剪后保留的任意 seq
    const maxTrimmed = Math.max(...seqsAfterTrim)
    const last3 = newSeqs.slice(-3)
    for (const s of last3) expect(s).toBeGreaterThan(maxTrimmed)
    // 新 3 条 seq 严格递增
    expect(last3[0]).toBeLessThan(last3[1])
    expect(last3[1]).toBeLessThan(last3[2])
  })

  // ─── P0-5 边界条件：内容解析 ───

  it('taskName 含冒号：只按第一个 ": " 拆分', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'deploy:v2: some content'))
    expect(result.current.logs[0].taskName).toBe('deploy:v2')
    expect(result.current.logs[0].content).toBe('some content')
  })

  it('内容本身含 ": " 前缀：不作为 taskName 拆分', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'foo: bar: baz'))
    expect(result.current.logs[0].taskName).toBe('foo')
    expect(result.current.logs[0].content).toBe('bar: baz')
  })

  it('仅冒号无空格：作为匿名日志全文保留', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'foo:bar'))
    expect(result.current.logs[0].taskName).toBe('')
    expect(result.current.logs[0].content).toBe('foo:bar')
  })

  it('单字符 taskName + 单字符 content', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'a: b'))
    expect(result.current.logs[0]).toMatchObject({ taskName: 'a', content: 'b' })
  })

  it('超长单行 content（10KB 不丢失）', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const long = 'x'.repeat(10_000)
    act(() => MockEventSource.instances[0].emit('log', `build: ${long}`))
    expect(result.current.logs[0].content).toHaveLength(10_000)
  })

  it('\r\n 换行符正确拆分，同时剥离 \r', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'build: a\r\nbuild: b\r\n\r\nbuild: c'))
    expect(result.current.logs).toHaveLength(4)
    expect(result.current.logs.map((l) => l.content)).toEqual(['a', 'build: b', '', 'build: c'])
  })

  it('\r 字符全局剥离（清理 \\r\\n 残留）', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'build: a\rbuild: b'))
    expect(result.current.logs).toHaveLength(1)
    expect(result.current.logs[0].content).toBe('abuild: b')
  })

  it('空行保留：仅过滤末尾空元素，中间空白行保留', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'build: a\n   \n\t\nbuild: b'))
    expect(result.current.logs).toHaveLength(4)
    expect(result.current.logs.map((l) => l.content)).toEqual(['a', '   ', '\t', 'build: b'])
  })

  it('混合 taskName：同一 batch 中不同前缀各行独立', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', 'build: a\nbuild: b'))
    // 同一 SSE 事件内部共享 taskName，即使多行
    expect(result.current.logs.map((l) => l.taskName)).toEqual(['build', 'build'])
    // 验证 seq 仍递增
    expect(result.current.logs[0].seq).toBeLessThan(result.current.logs[1].seq)
  })

  it('空字符串 SSE 事件：不追加任何日志', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    act(() => MockEventSource.instances[0].emit('log', ''))
    expect(result.current.logs).toHaveLength(0)
  })

  it('恰好 MAX_LOG_LINES 不触发裁剪', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    const lines: string[] = []
    for (let i = 0; i < 5000; i++) lines.push(`build: line${i}`)
    act(() => es.emit('log', lines.join('\n')))
    expect(result.current.logs).toHaveLength(5000)
  })

  it('多次小批量推送 + 逐批验证 seq 递增', () => {
    const { result } = renderHook(() => useSSELogs('run-1'))
    const es = MockEventSource.instances[0]
    for (let batch = 0; batch < 10; batch++) {
      act(() => es.emit('log', `task${batch}: a\ntask${batch}: b`))
    }
    expect(result.current.logs).toHaveLength(20)
    const seqs = result.current.logs.map((l) => l.seq)
    // 20 条 seq 全部唯一且严格递增
    expect(new Set(seqs).size).toBe(20)
    for (let i = 1; i < seqs.length; i++) {
      expect(seqs[i]).toBeGreaterThan(seqs[i - 1])
    }
  })
})
