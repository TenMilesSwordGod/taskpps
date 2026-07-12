import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import TrendLineChart from './TrendLineChart'

// jsdom 下 getBoundingClientRect 恒为 0，组件会回退到内置默认尺寸：
// width=600、chartH=height prop。故绘图区基线 = PAD_T + (chartH - PAD_T - PAD_B)
const PAD_T = 16
const PAD_B = 30
const CHART_H = 220
const BASELINE_Y = PAD_T + (CHART_H - PAD_T - PAD_B) // 190
const TOP_Y = PAD_T // 16

/** 从 path 的 d 属性里解析出所有 y 坐标（即每个 "x,y" 中的 y） */
function extractYValues(d: string): number[] {
  const ys: number[] = []
  const re = /(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(d)) !== null) {
    ys.push(parseFloat(m[2]))
  }
  return ys
}

function getLinePathD(container: HTMLElement): string {
  const svg = container.querySelector('svg')
  expect(svg).not.toBeNull()
  // 折线 path 使用 fill="none"；区域填充 path 使用渐变 fill，需排除
  const line = svg!.querySelector('path[fill="none"]')
  expect(line).not.toBeNull()
  return line!.getAttribute('d') ?? ''
}

describe('<TrendLineChart /> 平滑曲线不越过绘图区', () => {
  it('连续两个 0% 时曲线不冲到负值（不超过基线）', () => {
    // 100% -> 0% -> 0%：未修复时 Catmull-Rom 控制点会被推到基线之下（约 219px）
    const data = [
      { label: 'run1', value: 100 },
      { label: 'run2', value: 0 },
      { label: 'run3', value: 0 },
    ]
    const { container } = render(<TrendLineChart data={data} height={CHART_H} unit="%" />)
    const ys = extractYValues(getLinePathD(container))
    expect(ys.length).toBeGreaterThan(0)
    expect(Math.max(...ys)).toBeLessThanOrEqual(BASELINE_Y)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(TOP_Y)
  })

  it('全为 0% 时曲线贴在基线上、不出现下凹', () => {
    const data = [
      { label: 'run1', value: 0 },
      { label: 'run2', value: 0 },
      { label: 'run3', value: 0 },
    ]
    const { container } = render(<TrendLineChart data={data} height={CHART_H} unit="%" />)
    const ys = extractYValues(getLinePathD(container))
    expect(Math.max(...ys)).toBeLessThanOrEqual(BASELINE_Y)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(TOP_Y)
  })

  it('峰值序列不越过顶端', () => {
    const data = [
      { label: 'run1', value: 0 },
      { label: 'run2', value: 100 },
      { label: 'run3', value: 0 },
      { label: 'run4', value: 100 },
    ]
    const { container } = render(<TrendLineChart data={data} height={CHART_H} unit="%" />)
    const ys = extractYValues(getLinePathD(container))
    expect(Math.max(...ys)).toBeLessThanOrEqual(BASELINE_Y)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(TOP_Y)
  })
})