import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// 静默 jsdom "Not implemented: navigation" 警告（点击 <a download> 触发）
const originalError = console.error
console.error = (...args: unknown[]) => {
  const msg = typeof args[0] === 'string' ? args[0] : ''
  if (msg.includes('Not implemented: navigation')) return
  originalError(...(args as Parameters<typeof originalError>))
}

// 每个测试后自动卸载 React 树
afterEach(() => {
  cleanup()
})

// jsdom 不提供 matchMedia，AntD Layout 等组件会用到
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// jsdom 不实现 ResizeObserver，AntD Splitter 等组件会用到
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
;(globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver =
  ResizeObserverStub

// jsdom 不实现 getBoundingClientRect 真实尺寸：使用默认值
if (!('getBoundingClientRect' in HTMLElement.prototype)) {
  // @ts-expect-error jsdom fallback
  HTMLElement.prototype.getBoundingClientRect = function () {
    return { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }
  }
}

// jsdom 不实现 ClipboardItem，仅测试需要
class ClipboardItemStub {
  private readonly types: Record<string, Blob>
  constructor(items: Record<string, Blob>) {
    this.types = items
  }
  get types_list(): string[] {
    return Object.keys(this.types)
  }
}
;(globalThis as unknown as { ClipboardItem: typeof ClipboardItemStub }).ClipboardItem =
  ClipboardItemStub

