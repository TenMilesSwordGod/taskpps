import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TaskNode from '../TaskNode'
import type { TaskYAML } from '@/types'
import { useAppStore } from '@/stores/appStore'

// ReactFlow 的 Handle 组件依赖 ReactFlow store 上下文，单测中需 mock 为空组件
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

describe('TaskNode', () => {
  it('任务名正常渲染', () => {
    renderTaskNode(makeTask({ name: 'compile', command: 'make' }))
    expect(screen.getByText('compile')).toBeInTheDocument()
  })

  it('点击触发 setSelectedNodeId', () => {
    renderTaskNode(makeTask({ name: 'build' }), 'node-42')

    // 找到可点击的卡片 div（包含任务名）
    const card = screen.getByText('build').closest('div')!
    fireEvent.click(card)

    expect(useAppStore.getState().selectedNodeId).toBe('node-42')
  })

  it('有 when 属性时不渲染任何 when 相关元素', () => {
    renderTaskNode(makeTask({ when: '${env.ENABLE_LINT}' }))
    // TaskNode 不再渲染 when 药丸徽章，不应出现 skip、ENABLE_LINT 等 when 相关文本
    expect(screen.queryByText('skip')).not.toBeInTheDocument()
    expect(screen.queryByText('ENABLE_LINT')).not.toBeInTheDocument()
  })
})
