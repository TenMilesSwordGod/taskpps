/**
 * 成功率折线图点击跳转测试。
 *
 * 设计决策（为什么这么写）：
 * - 数据点必须通过真实路由跳转验证，而不是只断言 onClick 被调用，避免导航目标拼错。
 * - runs 采用“最近在前”的真实接口顺序，确保测试能捕获倒序绘制与点击索引错位的问题。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import SuccessRateChart from '../SuccessRateChart'
import type { RunSummary } from '../SuccessRateChart'

const runs: RunSummary[] = [
  {
    id: 'run-new',
    created_at: '2026-09-27T10:00:00+08:00',
    task_summary: { success: 2 },
  },
  {
    id: 'run-old',
    created_at: '2026-09-26T10:00:00+08:00',
    task_summary: { success: 1, failed: 1 },
  },
]

describe('<SuccessRateChart /> 点击跳转', () => {
  it('点击某个数据点后进入该次运行详情', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/pipelines']}>
        <Routes>
          <Route path="/pipelines" element={<SuccessRateChart runs={runs} />} />
          <Route path="/runs/:id" element={<div>运行详情页</div>} />
        </Routes>
      </MemoryRouter>,
    )

    // 折线图左旧右新，最左侧点对应数组中的第二条历史运行。
    await user.click(screen.getByRole('button', { name: /第 2 次运行/ }))

    expect(screen.getByText('运行详情页')).toBeInTheDocument()
  })
})
