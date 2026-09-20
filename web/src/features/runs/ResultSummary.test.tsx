import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ResultSummary from './ResultSummary'
import type { ResultPageResponse } from '@/types'

function makeData(overrides: Partial<ResultPageResponse['stats']> = {}): ResultPageResponse {
  return {
    run_id: 'run-1',
    pipeline_name: 'test-pipeline',
    status: 'partial',
    format: 'html',
    stats: {
      status: 'partial',
      status_display: '部分成功',
      pass_count: 12,
      fail_count: 3,
      blocked_count: 2,
      total_count: 17,
      started_at: '2026-09-12T14:20:00.000000+00:00',
      finished_at: '2026-09-12T14:23:42.000000+00:00',
      duration: '3m 42s',
      ...overrides,
    },
    html_content: '',
    md_content: '',
    collector_mode: null,
    has_collector: false,
    collector_html: null,
    collector_md: null,
    generated_at: null,
  }
}

describe('<ResultSummary />', () => {
  it('renders pipeline name, pass rate, metrics and duration', () => {
    render(<ResultSummary data={makeData()} />)
    expect(screen.getByText('test-pipeline')).toBeDefined()
    expect(screen.getByText('70.6%')).toBeDefined()
    expect(screen.getByText('通过')).toBeDefined()
    expect(screen.getByText('12')).toBeDefined()
    expect(screen.getByText('3')).toBeDefined()
    expect(screen.getByText('2')).toBeDefined()
    expect(screen.getByText('17')).toBeDefined()
    expect(screen.getByText('3m 42s')).toBeDefined()
  })

  it('shows meaningful empty state instead of a row of zeros', () => {
    render(
      <ResultSummary
        data={makeData({
          pass_count: 0,
          fail_count: 0,
          blocked_count: 0,
          total_count: 0,
          duration: '',
        })}
      />,
    )
    expect(screen.getByText('本次运行没有任务记录')).toBeDefined()
    expect(screen.queryByText('0.0%')).toBeNull()
  })

  it('exposes progress bar distribution to screen readers', () => {
    render(<ResultSummary data={makeData()} />)
    expect(
      screen.getByRole('img', { name: '任务分布：通过 12，失败 3，阻塞 2，总计 17' }),
    ).toBeDefined()
  })

  it('formats times locally and shows - for missing time', () => {
    render(
      <ResultSummary
        data={makeData({ started_at: null, finished_at: null })}
      />,
    )
    expect(screen.getByText('开始')).toBeDefined()
    expect(screen.getByText('结束')).toBeDefined()
    expect(screen.getAllByText('-').length).toBe(2)
  })
})
