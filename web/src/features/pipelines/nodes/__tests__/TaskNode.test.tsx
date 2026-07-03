import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TaskNode from '../TaskNode'
import type { TaskYAML } from '@/types'

// ReactFlow 的 Handle 组件依赖 ReactFlow store 上下文，单测中需 mock 为空组件
// 注意：vi.mock 工厂被 hoist 到文件顶部，不能使用 JSX（会破坏 transform），用 null 替代
vi.mock('@xyflow/react', () => ({
  Handle: () => null,
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
}))

/** 构造最小合法 TaskYAML */
function makeTask(overrides: Partial<TaskYAML> = {}): TaskYAML {
  return {
    name: 'test-task',
    env: {},
    retry: 0,
    depends_on: [],
    ...overrides,
  }
}

/** 渲染 TaskNode 的辅助函数 */
function renderTaskNode(task: TaskYAML, id = 'test-node') {
  return render(<TaskNode id={id} data={{ task, subpipelineName: 'build', order: 1 }} />)
}

describe('TaskNode — when 表达式不在节点内部渲染', () => {
  it('有 when 时不显示 task-when 元素', () => {
    const when = '${env.ENABLE_LINT}'
    renderTaskNode(makeTask({ when }))
    expect(screen.queryByTestId('task-when')).not.toBeInTheDocument()
  })

  it('有 when 时不在节点文本中显示 when 表达式', () => {
    const when = '${env.ENABLE_LINT}'
    renderTaskNode(makeTask({ when }))
    expect(screen.queryByText(when)).not.toBeInTheDocument()
  })

  it('无 when 时与现有结构一致', () => {
    renderTaskNode(makeTask())
    expect(screen.queryByTestId('task-when')).not.toBeInTheDocument()
  })

  it('任务名与类型标签仍正常渲染', () => {
    renderTaskNode(makeTask({ name: 'compile', command: 'make' }))
    expect(screen.getByText('compile')).toBeInTheDocument()
    expect(screen.getByText('命令')).toBeInTheDocument()
  })
})
