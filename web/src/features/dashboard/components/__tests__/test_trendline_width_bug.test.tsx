import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'
import TrendLineChart from '../TrendLineChart'

/**
 * 运行走势折线图「宽度测量时机 + 绘制动画」缺陷回归测试（对应 Gitea issue #193）。
 *
 * 根因（代码走查确认，非盲从）：
 *  - 初始 `useState({ w: 600 })`（TrendLineChart.tsx:68）为硬编码默认宽度；
 *  - `useLayoutEffect` 挂载时测容器真实宽度（行 105-113），但首次进入仪表盘父级 flex
 *    布局尚未就绪，`getBoundingClientRect()` 返回 0 → 回退默认 600，折线 path 只画到
 *    ~588（真实容器 ≈1487）→ 右侧大片留白；导航返回重挂载才拿到真实宽度；
 *  - 绘制动画 effect 仅依赖 `dataSignature`（行 79-102），width 变化（600→1487）不重播，
 *    导致 `stroke-dashoffset` 长度与重算后 path 长度不匹配 → 折线只画一半 / 绘制方向异常。
 *
 * 测试策略（headless/jsdom 无法复现真实布局时序，故 mock getBoundingClientRect /
 * ResizeObserver / getTotalLength 证明根因）：
 *  - 用可控的 mock 容器宽度模拟「首次进入宽度未就绪」与「ResizeObserver 上报真实宽度」；
 *  - 用 path 的 `d` 最大 x 坐标作为路径长度代理，断言折线在宽度变化后「铺满 + 动画重播」。
 *
 * 这些测试在修复前应为【红】，修复后应为【绿】（TDD）。
 */

// ---- 可控 mock：容器真实尺寸 ----
let mockWidth = 600
let mockHeight = 220

// ---- ResizeObserver mock：手动触发，模拟浏览器在布局稳定后上报真实宽度 ----
class ResizeObserverMock {
  cb: ResizeObserverCallback
  static instances: ResizeObserverMock[] = []
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb
    ResizeObserverMock.instances.push(this)
  }
  observe() {}
  unobserve() {}
  disconnect() {}
  /** 模拟容器尺寸变化（contentRect 为真实测量值） */
  trigger(width: number, height: number) {
    this.cb(
      [
        {
          contentRect: { width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0 },
        },
      ] as unknown as ResizeObserverEntry[],
      this as unknown as ResizeObserver,
    )
  }
}

const SAMPLE = [
  { label: '周一', value: 10 },
  { label: '周二', value: 20 },
  { label: '周三', value: 15 },
  { label: '周四', value: 30 },
  { label: '周五', value: 25 },
  { label: '周六', value: 35 },
  { label: '周日', value: 28 },
]

/** 取折线 path（fill="none" 的那个，区别于区域填充 path） */
function getLinePath(container: HTMLElement): SVGPathElement {
  const svg = container.querySelector('svg')
  expect(svg).not.toBeNull()
  const line = svg!.querySelector('path[fill="none"]') as SVGPathElement | null
  expect(line).not.toBeNull()
  return line!
}

/** 从 path 的 d 属性解析最大 x 坐标（作为路径长度单调代理） */
function getPathMaxX(d: string): number {
  let maxX = 0
  const re = /(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(d)) !== null) maxX = Math.max(maxX, parseFloat(m[1]))
  return maxX
}

function installDomMocks() {
  // 所有元素 getBoundingClientRect 返回当前可控容器尺寸
  ;(HTMLElement.prototype as unknown as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect =
    function () {
      return {
        top: 0,
        left: 0,
        right: mockWidth,
        bottom: mockHeight,
        x: 0,
        y: 0,
        width: mockWidth,
        height: mockHeight,
        toJSON: () => ({}),
      } as DOMRect
    }

  // getTotalLength 返回 path d 的最大 x 坐标（与宽度单调相关，作为长度代理）。
  // 这样折线 dash 长度 = 当前渲染宽度对应长度，宽度变化后旧 dash 会与新 path 失配。
  Object.defineProperty(SVGElement.prototype, 'getTotalLength', {
    configurable: true,
    writable: true,
    value: function () {
      const d = (this.getAttribute?.('d') as string) || ''
      return getPathMaxX(d) || 1
    },
  })
}

beforeEach(() => {
  ResizeObserverMock.instances = []
  // 覆盖 setup.ts 的 ResizeObserver 桩，改为可手动触发的 mock
  ;(globalThis as unknown as { ResizeObserver: typeof ResizeObserverMock }).ResizeObserver =
    ResizeObserverMock
  installDomMocks()
  // 用 fake timers 冻结动画清理定时器（950ms 后 dash 会被清成 none），
  // 以便稳定断言「宽度变化后 dash 是否随新路径重设」
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

/** 折线是否完整可见（无右侧留白缺口）：dash=none 或 dash 长度 ≥ 当前路径长度 */
function isFullyDrawn(line: SVGPathElement): boolean {
  const dash = line.style.strokeDasharray
  if (dash === 'none') return true
  const dashNum = Number(dash)
  const pathLen = line.getTotalLength()
  return Number.isFinite(dashNum) && dashNum >= pathLen
}

describe('issue #193 运行走势折线图 宽度/动画缺陷', () => {
  // 场景 (a)：首次挂载容器宽度未就绪（回退默认 600 半宽），
  // ResizeObserver 上报真实宽度后折线必须铺满，且绘制动画 dash 重设到完整路径长度
  it('a) 首次进入宽度未就绪时不应永久停在默认600半宽，真实宽度上报后应铺满并完整绘制', () => {
    // 模拟「首次进入仪表盘」：父级 flex 布局尚未就绪，挂载时测得宽度为 0
    mockWidth = 0
    mockHeight = 0

    const { container } = render(<TrendLineChart data={SAMPLE} height={220} unit="次" />)

    // 初始回退默认 600：折线几何宽度 ≈ 600-12=588，只画一半
    const lineBefore = getLinePath(container)
    expect(getPathMaxX(lineBefore.getAttribute('d')!)).toBeLessThanOrEqual(600)

    // 模拟浏览器布局稳定后 ResizeObserver 上报真实容器宽度（≈1487）
    act(() => {
      ResizeObserverMock.instances.forEach((r) => r.trigger(1487, 220))
    })

    const lineAfter = getLinePath(container)
    const maxX = getPathMaxX(lineAfter.getAttribute('d')!)

    // 几何上应已铺满真实宽度（≈1475），不再停在 600 半宽
    expect(maxX).toBeGreaterThan(1000)

    // 关键：绘制动画 dash 必须随新宽度重设，覆盖完整折线（不应仍是 600 半宽 dash 导致右侧留白）
    expect(isFullyDrawn(lineAfter)).toBe(true)
  })

  // 场景 (b)：宽度变化（600→1487）后，绘制动画应「重新播放」（自左起点顺序绘制），
  // 即 dash 必须重设到新路径长度，而非沿用旧 600 半宽 dash（会造成异常方向/只画一半）
  it('b) 容器宽度变化后绘制动画应重播：dash 重设到新路径长度（自左起点顺序绘制）', () => {
    // 初始挂载即拿到 600（模拟某次渲染基准宽度）
    mockWidth = 600
    mockHeight = 220

    const { container } = render(<TrendLineChart data={SAMPLE} height={220} unit="次" />)
    const lineInitial = getLinePath(container)
    // 初次动画已按 600 宽路径设置 dash
    expect(Number(lineInitial.style.strokeDasharray)).toBeGreaterThan(0)

    // 容器宽度变化到 1487（真实场景：窗口/布局变化或导航重挂载拿到真实宽度）
    act(() => {
      ResizeObserverMock.instances.forEach((r) => r.trigger(1487, 220))
    })

    const lineAfter = getLinePath(container)
    const maxX = getPathMaxX(lineAfter.getAttribute('d')!)
    expect(maxX).toBeGreaterThan(1000)

    // 宽度变化后，绘制动画应当重新播放：dash 重设到「新路径长度」(或清成 none 视为完整可见)
    // 修复前：effect 仅在 dataSignature 变化时重跑，dash 停留在旧 600 半宽 → 失败
    const dash = lineAfter.style.strokeDasharray
    const pathLen = lineAfter.getTotalLength()
    const replayed = dash === 'none' || Number(dash) === pathLen
    expect(replayed).toBe(true)
  })
})
