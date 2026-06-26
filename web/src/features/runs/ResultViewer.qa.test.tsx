/**
 * QA independent tests for ResultViewer component.
 * Covers 4 dimensions: Boundary / Exception / Concurrency / Environment.
 * No overlap with developer's tests in ResultViewer.test.tsx.
 *
 * Mapped to zentao testcase TC-W1000 (case_1577).
 */
import { describe, it, expect } from 'vitest'
import { render, screen, act } from '@testing-library/react'
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

// ══════════════════════════════════════════════════════
// 1. BOUNDARY
// ══════════════════════════════════════════════════════

describe('ResultViewer QA Boundary', () => {
  it('renders very long HTML content without crash', () => {
    const longContent = '<h1>Long</h1>' + '<p>' + 'A'.repeat(50000) + '</p>'
    const data = makeResultPage({ html_content: longContent })
    render(<ResultViewer data={data} />)
    expect(document.querySelector('.flex-1.overflow-auto')).toBeTruthy()
  })

  it('renders very long MD content without crash', () => {
    const longMd = '# Long\n\n' + 'A'.repeat(50000)
    const data = makeResultPage({ format: 'md', md_content: longMd, html_content: '' })
    render(<ResultViewer data={data} />)
    expect(document.querySelector('.flex-1.overflow-auto')).toBeTruthy()
  })

  it('renders pipeline name with special characters', () => {
    const data = makeResultPage({ pipeline_name: '测试🔥 #154 — <Result> & "Page"' })
    render(<ResultViewer data={data} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('handles zero counts gracefully', () => {
    const zero = makeResultPage({
      stats: {
        status: 'success',
        status_display: '成功',
        pass_count: 0,
        fail_count: 0,
        blocked_count: 0,
        total_count: 0,
        started_at: null,
        finished_at: null,
        duration: '',
      },
    })
    render(<ResultViewer data={zero} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('handles very large numbers in stats', () => {
    const big = makeResultPage({
      stats: {
        status: 'success',
        status_display: '成功',
        pass_count: 99999999,
        fail_count: 99999999,
        blocked_count: 99999999,
        total_count: 299999997,
        started_at: '2024-01-01T00:00:00',
        finished_at: '2024-01-01T00:00:01',
        duration: '1s',
      },
    })
    render(<ResultViewer data={big} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('handles HTML with unclosed tags', () => {
    const broken = makeResultPage({ html_content: '<h1>Title<p>para<b>bold' })
    render(<ResultViewer data={broken} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('Title')
  })

  it('handles MD with empty code block', () => {
    const mdWithEmpty = makeResultPage({
      format: 'md',
      md_content: '# Test\n\n```\n\n```\n\nOK',
      html_content: '',
    })
    render(<ResultViewer data={mdWithEmpty} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('handles MD with table', () => {
    const mdTable = makeResultPage({
      format: 'md',
      md_content: '# Table\n\n| Col A | Col B |\n|------|------|\n| val1 | val2 |\n| val3 | val4 |',
      html_content: '',
    })
    render(<ResultViewer data={mdTable} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('handles HTML with nested allowed tags', () => {
    const nested = makeResultPage({
      html_content: '<div><table><tr><td><strong>data</strong></td></tr></table></div>',
    })
    render(<ResultViewer data={nested} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('data')
  })
})

// ══════════════════════════════════════════════════════
// 2. EXCEPTION
// ══════════════════════════════════════════════════════

describe('ResultViewer QA Exception', () => {
  it('strips script tags from HTML content', () => {
    const risky = makeResultPage({
      html_content: '<h1>Safe</h1><script>alert("xss")</script>',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('<script')
    expect(container?.innerHTML).toContain('Safe')
  })

  it('strips iframe tags from HTML content', () => {
    const risky = makeResultPage({
      html_content: '<h1>Safe</h1><iframe src="http://evil.com"></iframe>',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('<iframe')
    expect(container?.innerHTML).not.toContain('iframe')
  })

  it('strips object tags from HTML content', () => {
    const risky = makeResultPage({
      html_content: '<h1>Safe</h1><object data="evil.swf"></object>',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('<object')
  })

  it('strips event handler attributes (onclick)', () => {
    const risky = makeResultPage({
      html_content: '<h1 onclick="alert(1)">Click me</h1>',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('onclick')
    expect(container?.innerHTML).toContain('Click me')
  })

  it('strips javascript: protocol from href', () => {
    const risky = makeResultPage({
      html_content: '<a href="javascript:alert(1)">link</a>',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('javascript:alert')
    expect(container?.innerHTML).toContain('link')
  })

  it('handles HTML with form tag', () => {
    const risky = makeResultPage({
      html_content: '<form action="bad"><input name="user" /></form>',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('<form')
    expect(container?.innerHTML).not.toContain('<input')
  })

  it('handles HTML with embed tag', () => {
    const risky = makeResultPage({
      html_content: '<h1>Safe</h1><embed src="evil.swf" />',
    })
    render(<ResultViewer data={risky} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).not.toContain('<embed')
  })

  it('handles empty html_content and md_content', () => {
    const empty = makeResultPage({ html_content: '', md_content: '' })
    render(<ResultViewer data={empty} />)
    expect(screen.getByText('执行结果')).toBeDefined()
  })
})

// ══════════════════════════════════════════════════════
// 3. CONCURRENCY
// ══════════════════════════════════════════════════════

describe('ResultViewer QA Concurrency', () => {
  it('handles rapid re-render with different data', () => {
    const { rerender } = render(
      <ResultViewer data={makeResultPage({ run_id: 'run-1' })} />,
    )

    for (let i = 0; i < 10; i++) {
      const newData = makeResultPage({
        run_id: `run-${i}`,
        status: i % 2 === 0 ? 'success' : 'failed',
        html_content: `<h1>Run ${i}</h1>`,
      })
      rerender(<ResultViewer data={newData} />)
    }

    expect(screen.getByText('执行结果')).toBeDefined()
  })

  it('handles rapid HTML/MD format switching via re-render', () => {
    const { rerender } = render(
      <ResultViewer data={makeResultPage({ format: 'html' })} />,
    )

    for (let i = 0; i < 20; i++) {
      act(() => {
        const fmt = i % 2 === 0 ? 'html' as const : 'md' as const
        rerender(<ResultViewer data={makeResultPage({ format: fmt })} />)
      })
    }

    expect(screen.getByText('执行结果')).toBeDefined()
  })
})

// ══════════════════════════════════════════════════════
// 4. ENVIRONMENT
// ══════════════════════════════════════════════════════

describe('ResultViewer QA Environment', () => {
  it('shows no collector badge when has_collector is false', () => {
    const data = makeResultPage({ has_collector: false })
    render(<ResultViewer data={data} />)
    expect(screen.queryByText('Replaced')).toBeNull()
    expect(screen.queryByText('Appended')).toBeNull()
  })

  it('shows Appended badge for append mode', () => {
    const data = makeResultPage({ has_collector: true, collector_mode: 'append' })
    render(<ResultViewer data={data} />)
    expect(screen.getByText('Appended')).toBeDefined()
  })

  it('shows Replaced badge for replace mode', () => {
    const data = makeResultPage({ has_collector: true, collector_mode: 'replace' })
    render(<ResultViewer data={data} />)
    expect(screen.getByText('Replaced')).toBeDefined()
  })

  it('shows empty state for null/undefined data', () => {
    // @ts-expect-error testing null state - component should render empty state gracefully
    render(<ResultViewer data={null as unknown as ResultPageResponse} />)
    expect(screen.getByText('暂无结果数据')).toBeDefined()
  })

  it('renders HTML content directly when format is html', () => {
    const data = makeResultPage({ format: 'html' })
    render(<ResultViewer data={data} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('Test Result')
  })

  it('renders MD content as HTML when format is md', () => {
    const data = makeResultPage({ format: 'md', html_content: '' })
    render(<ResultViewer data={data} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('Test Result')
  })

  it('MD content renders code blocks as pre/code tags', () => {
    const mdCode = makeResultPage({
      format: 'md',
      md_content: '# Code Test\n\n```typescript\nconst x: number = 1;\n```',
      html_content: '',
    })
    render(<ResultViewer data={mdCode} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('<pre>')
    expect(container?.innerHTML).toContain('<code')
    expect(container?.innerHTML).toContain('const x')
  })

  it('MD content renders links correctly', () => {
    const mdLink = makeResultPage({
      format: 'md',
      md_content: '# Link\n\n[Click here](http://example.com)',
      html_content: '',
    })
    render(<ResultViewer data={mdLink} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('example.com')
  })

  it('MD content renders images correctly as img tags', () => {
    const mdImg = makeResultPage({
      format: 'md',
      md_content: '# Image\n\n![Alt text](http://example.com/img.png)',
      html_content: '',
    })
    render(<ResultViewer data={mdImg} />)
    const container = document.querySelector('.flex-1.overflow-auto')
    expect(container?.innerHTML).toContain('<img')
    expect(container?.innerHTML).toContain('Alt text')
    expect(container?.innerHTML).toContain('example.com/img.png')
  })
})
