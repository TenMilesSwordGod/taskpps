import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import BreadcrumbSwitcher from './BreadcrumbSwitcher'
import type { BreadcrumbSwitchItem } from './BreadcrumbSwitcher'

/** 构造测试用面包屑项 */
function makeItems(): BreadcrumbSwitchItem[] {
  return [
    { label: '首页', href: '/home' },
    {
      label: '项目A',
      options: [
        { key: 'p1', label: '项目A' },
        { key: 'p2', label: '项目B' },
        { key: 'p3', label: '项目C' },
      ],
      currentKey: 'p1',
      onSwitch: vi.fn(),
      popoverTitle: '切换项目',
    },
    { label: '流水线X' },
  ]
}

describe('<BreadcrumbSwitcher />', () => {
  it('渲染面包屑项标签', () => {
    render(<BreadcrumbSwitcher items={makeItems()} />)
    expect(screen.getByText('首页')).toBeInTheDocument()
    expect(screen.getByText('项目A')).toBeInTheDocument()
    expect(screen.getByText('流水线X')).toBeInTheDocument()
  })

  it('链接项有 href 属性', () => {
    render(<BreadcrumbSwitcher items={makeItems()} />)
    const link = screen.getByText('首页').closest('a')
    expect(link).toHaveAttribute('href', '/home')
  })

  it('悬浮 300ms 后弹出浮窗', async () => {
    render(<BreadcrumbSwitcher items={makeItems()} />)
    const hoverTarget = screen.getByTestId('crumb-hover-项目A')
    fireEvent.mouseEnter(hoverTarget)
    // antd Popover 的 mouseEnterDelay 为 0.3s，需等待
    await waitFor(() => {
      expect(screen.getByTestId('popover-content')).toBeInTheDocument()
    }, { timeout: 500 })
  })

  it('浮窗内搜索框过滤选项', async () => {
    const onSwitch = vi.fn()
    render(
      <BreadcrumbSwitcher
        items={[
          {
            label: '项目',
            options: [
              { key: 'a', label: 'Alpha' },
              { key: 'b', label: 'Beta' },
              { key: 'c', label: 'Ceta' },
            ],
            currentKey: 'a',
            onSwitch,
            popoverTitle: '切换',
          },
        ]}
      />,
    )
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-项目'))
    await waitFor(() => {
      expect(screen.getByTestId('popover-content')).toBeInTheDocument()
    }, { timeout: 500 })

    // 搜索 "et"
    const searchInput = screen.getByTestId('popover-search')
    fireEvent.change(searchInput, { target: { value: 'et' } })

    await waitFor(() => {
      expect(screen.queryByTestId('popover-option-a')).not.toBeInTheDocument()
      expect(screen.getByTestId('popover-option-b')).toBeInTheDocument()
      expect(screen.getByTestId('popover-option-c')).toBeInTheDocument()
    })
  })

  it('选项切换调用 onSwitch', async () => {
    const onSwitch = vi.fn()
    render(
      <BreadcrumbSwitcher
        items={[
          {
            label: '项目',
            options: [
              { key: 'a', label: 'Alpha' },
              { key: 'b', label: 'Beta' },
            ],
            currentKey: 'a',
            onSwitch,
          },
        ]}
      />,
    )
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-项目'))
    await waitFor(() => {
      expect(screen.getByTestId('popover-content')).toBeInTheDocument()
    }, { timeout: 500 })

    fireEvent.click(screen.getByTestId('popover-option-b'))
    expect(onSwitch).toHaveBeenCalledWith('b')
  })

  it('当前选中项有蓝色圆点指示器', async () => {
    render(
      <BreadcrumbSwitcher
        items={[
          {
            label: '项目',
            options: [
              { key: 'a', label: 'Alpha' },
              { key: 'b', label: 'Beta' },
            ],
            currentKey: 'a',
          },
        ]}
      />,
    )
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-项目'))
    await waitFor(() => {
      expect(screen.getByTestId('popover-content')).toBeInTheDocument()
    }, { timeout: 500 })

    const dotA = screen.getByTestId('dot-a')
    expect(dotA.className).toContain('bg-blue-500')
    const dotB = screen.getByTestId('dot-b')
    expect(dotB.className).toContain('bg-transparent')
  })

  it('无匹配结果时显示 empty 状态', async () => {
    render(
      <BreadcrumbSwitcher
        items={[
          {
            label: '项目',
            options: [{ key: 'a', label: 'Alpha' }],
            currentKey: 'a',
          },
        ]}
      />,
    )
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-项目'))
    await waitFor(() => {
      expect(screen.getByTestId('popover-content')).toBeInTheDocument()
    }, { timeout: 500 })

    fireEvent.change(screen.getByTestId('popover-search'), { target: { value: 'zzz' } })
    await waitFor(() => {
      expect(screen.getByTestId('popover-empty')).toBeInTheDocument()
    })
  })

  it('loading 时显示骨架', async () => {
    render(
      <BreadcrumbSwitcher
        items={[
          {
            label: '项目',
            options: [],
            currentKey: '',
            loading: true,
          },
        ]}
      />,
    )
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-项目'))
    await waitFor(
      () => {
        // antd Skeleton 渲染带动画的 placeholder
        const skeleton = document.querySelector('.ant-skeleton')
        expect(skeleton).toBeInTheDocument()
      },
      { timeout: 500 },
    )
  })

  it('onClick 项点击触发回调', () => {
    const onClick = vi.fn()
    render(<BreadcrumbSwitcher items={[{ label: '点击我', onClick }]} />)
    fireEvent.click(screen.getByText('点击我'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('末项不显示分隔符 /', () => {
    render(<BreadcrumbSwitcher items={makeItems()} />)
    const separators = document.querySelectorAll('.text-gray-300')
    // 3 个项 → 2 个分隔符
    expect(separators.length).toBe(2)
  })

  it('大于 20 条选项时初始显示 20 条并可滚动加载更多', async () => {
    const opts = Array.from({ length: 25 }, (_, i) => ({ key: `k${i}`, label: `选项${i}` }))
    render(
      <BreadcrumbSwitcher
        items={[
          {
            label: '列表',
            options: opts,
            currentKey: 'k0',
          },
        ]}
      />,
    )
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-列表'))
    await waitFor(() => {
      expect(screen.getByTestId('popover-content')).toBeInTheDocument()
    }, { timeout: 500 })

    // 初始 20 条可见
    expect(screen.getByTestId('popover-option-k0')).toBeInTheDocument()
    expect(screen.getByTestId('popover-option-k19')).toBeInTheDocument()
    expect(screen.queryByTestId('popover-option-k20')).not.toBeInTheDocument()

    // 滚动到底部触发加载更多
    const list = screen.getByTestId('popover-list')
    // 模拟滚动到底部
    Object.defineProperty(list, 'scrollHeight', { value: 800, writable: true })
    Object.defineProperty(list, 'scrollTop', { value: 800, writable: true })
    Object.defineProperty(list, 'clientHeight', { value: 200, writable: true })
    act(() => {
      list.dispatchEvent(new Event('scroll', { bubbles: true }))
    })

    await waitFor(() => {
      // 滚动加载更多后，k20-k24 应该可见
      expect(screen.getByTestId('popover-option-k20')).toBeInTheDocument()
    })
  })
})
