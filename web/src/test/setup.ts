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

// jsdom 不实现 SVG 几何接口（SVGPathElement/SVGGeometryElement），
// 折线图绘制动画调用 path.getTotalLength()，在 SVGElement 原型上统一桩
if (typeof SVGElement !== 'undefined' && typeof SVGElement.prototype.getTotalLength !== 'function') {
  Object.defineProperty(SVGElement.prototype, 'getTotalLength', {
    value: () => 0,
    configurable: true,
    writable: true,
  })
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

// jsdom 不实现 DataTransfer，拖拽测试需要
class DataTransferStub {
  private _data: Map<string, string> = new Map()
  dropEffect: string = 'none'
  effectAllowed: string = 'none'

  getData(format: string): string {
    return this._data.get(format) || ''
  }
  setData(format: string, data: string): void {
    this._data.set(format, data)
  }
  clearData(): void {
    this._data.clear()
  }
  get types(): string[] {
    return Array.from(this._data.keys())
  }
  get files(): File[] {
    return []
  }
  get items(): unknown[] {
    return []
  }
}
// @ts-expect-error jsdom fallback for DataTransfer
globalThis.DataTransfer = DataTransferStub

// jsdom 不实现 DOMMatrixReadOnly/DOMMatrix，ReactFlow updateNodeInternals 在解析
// CSS transform 时需要用到（commit 阶段的 passive effect 中调用）。
// 这里提供一个最小桩，让 new DOMMatrixReadOnly(transformString) 不抛错。
if (typeof window.DOMMatrixReadOnly !== 'function') {
  // 注意(2026-07): 最小桩，仅满足 ReactFlow 的构造函数调用，不做实际矩阵运算。
  // 若后续有矩阵运算需求（inverse/multiply 等），需补充对应方法。
  class DOMMatrixReadOnlyStub {
    a = 1; b = 0; c = 0; d = 1; e = 0; f = 0;
    static fromMatrix() { return new DOMMatrixReadOnlyStub(); }
    static fromFloat64Array() { return new DOMMatrixReadOnlyStub(); }
    static fromFloat32Array() { return new DOMMatrixReadOnlyStub(); }
    inverse() { return new DOMMatrixReadOnlyStub(); }
    multiply() { return new DOMMatrixReadOnlyStub(); }
    translate() { return new DOMMatrixReadOnlyStub(); }
    scale() { return new DOMMatrixReadOnlyStub(); }
    rotate() { return new DOMMatrixReadOnlyStub(); }
    flipX() { return new DOMMatrixReadOnlyStub(); }
    flipY() { return new DOMMatrixReadOnlyStub(); }
    toJSON() { return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }; }
    toString() { return 'matrix(1, 0, 0, 1, 0, 0)'; }
  }
  // @ts-expect-error jsdom fallback
  window.DOMMatrixReadOnly = DOMMatrixReadOnlyStub;
}
if (typeof window.DOMMatrix !== 'function') {
  class DOMMatrixStub extends (window.DOMMatrixReadOnly as unknown as new () => unknown) {
    constructor(init?: string | number[]) {
      super();
    }
    static fromMatrix() { return new DOMMatrixStub(); }
    static fromFloat64Array() { return new DOMMatrixStub(); }
    static fromFloat32Array() { return new DOMMatrixStub(); }
  }
  // @ts-expect-error jsdom fallback
  window.DOMMatrix = DOMMatrixStub;
  // @ts-expect-error jsdom also missing on globalThis
  globalThis.DOMMatrix = DOMMatrixStub;
}

