/**
 * LogViewer UX 补测（2026-09，QA 审计）。
 *
 * 覆盖维度：空态 / 过滤无结果 / 操作禁用 / 连接状态反馈。
 * 背景：现有用例只覆盖任务颜色分配与复制按钮显隐；日志为空/过滤无匹配/
 * 无日志导出禁用等体验点零断言，SSE 断开更是完全无可见反馈，故新增本文件。
 * v2 (2026-09, issue #220): 断开提示已实现，用例已转为常规断言。
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import LogViewer from './LogViewer'
import type { LogEntry } from './hooks/useSSELogs'

// 注意(v2, 2026-09): vitest 配置 css:false 会把 `?raw` 导入也桩成空串，
// 因此直接读磁盘上的 index.css 原文做规则断言（vitest cwd 即 web 根目录）。
const indexCss = readFileSync(path.resolve(process.cwd(), 'src/index.css'), 'utf-8')

function makeLog(seq: number, taskName: string, content: string): LogEntry {
  return { seq, taskName, content, timestamp: Date.now() + seq }
}

const baseProps = {
  connected: true,
  onClear: vi.fn(),
}

describe('<LogViewer /> UX-空态', () => {
  it('UX-无日志时展示「暂无日志输出」', () => {
    render(<LogViewer logs={[]} {...baseProps} />)
    expect(screen.getByText('暂无日志输出')).toBeInTheDocument()
  })

  it('UX-有日志但过滤无匹配时展示「无匹配日志」并保留总行数', () => {
    const logs = [makeLog(1, 'task-a', 'hello')]
    render(<LogViewer logs={logs} {...baseProps} selectedTaskId="task-b" />)
    expect(screen.getByText('无匹配日志')).toBeInTheDocument()
    expect(screen.getByText(/0 \/ 1 行/)).toBeInTheDocument()
  })
})

describe('<LogViewer /> UX-操作禁用', () => {
  it('UX-无日志时复制与导出按钮均禁用', () => {
    render(<LogViewer logs={[]} {...baseProps} onCopyLogs={vi.fn()} />)
    expect(screen.getByRole('button', { name: /复制/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /导出/ })).toBeDisabled()
  })

  it('UX-有日志时复制与导出按钮可用', () => {
    render(<LogViewer logs={[makeLog(1, 'task-a', 'hello')]} {...baseProps} onCopyLogs={vi.fn()} />)
    expect(screen.getByRole('button', { name: /复制/ })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: /导出/ })).not.toBeDisabled()
  })
})

describe('<LogViewer /> UX-连接状态反馈', () => {
  it('UX-连接断开时展示明确的断开提示（而非仅隐藏「已连接」）', () => {
    render(<LogViewer logs={[makeLog(1, 'task-a', 'hello')]} {...baseProps} connected={false} />)

    expect(screen.queryByText('已连接')).not.toBeInTheDocument()
    expect(screen.getByText(/连接已断开|已断开|重连中/)).toBeInTheDocument()
  })
})

/**
 * Bug: 深色日志区里选中文本（复制日志）看不到选区高亮。
 * 全局 ::selection 用 rgba(31,31,31,0.25) 黑灰半透明，在 #111827 深底上几乎无对比；
 * 修复要求 LogViewer 根节点暴露 log-viewer 类，并由 index.css 为其定义亮色选区。
 * jsdom 无法计算 ::selection 伪元素样式，故直接校验「类名挂载 + 样式规则存在」这一契约。
 */
describe('<LogViewer /> UX-深色日志区选区高亮', () => {
  it('UX-日志面板根节点带 log-viewer 类，且样式表为深色底定义了亮色 ::selection', () => {
    const { container } = render(<LogViewer logs={[makeLog(1, 'task-a', 'hello')]} {...baseProps} />)

    expect(container.querySelector('.log-viewer')).toBeInTheDocument()

    const rule = indexCss.match(/\.log-viewer\s+::selection\s*\{([^}]*)\}/)
    expect(rule, 'index.css 缺少 .log-viewer ::selection 规则').not.toBeNull()
    expect(rule![1]).toMatch(/background:\s*rgba\(\s*255/)
  })
})
