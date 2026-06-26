import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ResultViewer from './ResultViewer'
import type { ResultPageResponse } from '@/types'

function makeResultPage(overrides: Partial<ResultPageResponse> = {}): ResultPageResponse {
  return {
    run_id: 'run-1',
    pipeline_name: 'test-pipeline',
    status: 'success',
    format: 'html',
    stats: {
      status: 'success',
      status_display: '成功',
      pass_count: 3,
      fail_count: 0,
      blocked_count: 0,
      total_count: 3,
      started_at: '2024-01-01T00:00:00',
      finished_at: '2024-01-01T00:01:00',
      duration: '1m 0s',
    },
    html_content: '<h1>Test Result</h1><p>All tests passed.</p>',
    md_content: '# Test Result\n\nAll tests passed.',
    collector_mode: null,
    has_collector: false,
    generated_at: '2024-01-01T00:01:00',
    ...overrides,
  }
}

describe('<ResultViewer />', () => {
  it('renders html content by default', () => {
    const data = makeResultPage()
    render(<ResultViewer data={data} />)
    expect(screen.getByText('执行结果')).toBeDefined()
    const htmlContent = document.querySelector('.flex-1.overflow-auto')
    expect(htmlContent?.innerHTML).toContain('Test Result')
  })

  it('renders md content when format is md', () => {
    const data = makeResultPage({
      format: 'md',
      html_content: '',
      md_content: '# MD Title\n\nHello **world**.',
    })
    render(<ResultViewer data={data} />)
    expect(screen.getByText('执行结果')).toBeDefined()
    const htmlContent = document.querySelector('.flex-1.overflow-auto')
    expect(htmlContent?.innerHTML).toContain('MD Title')
  })

  it('shows collector badge when has_collector is true', () => {
    const data = makeResultPage({ has_collector: true, collector_mode: 'replace' })
    render(<ResultViewer data={data} />)
    expect(screen.getByText('Replaced')).toBeDefined()
  })

  it('shows empty state when no data provided', () => {
    const data = makeResultPage({ html_content: '', md_content: '' })
    render(<ResultViewer data={data} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('shows 暂无结果数据 when data is null', () => {
    render(<ResultViewer data={null as unknown as ResultPageResponse} />)
    expect(screen.getByText('暂无结果数据')).toBeDefined()
  })
})
