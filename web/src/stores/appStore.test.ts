import { describe, it, expect, beforeEach } from 'vitest'
import { useAppStore } from '@/stores/appStore'

describe('useAppStore', () => {
  beforeEach(() => {
    // 重置到初始值（zustand store 是模块级单例）
    useAppStore.setState({
      selectedNodeId: null,
      panelWidth: 420,
      panelMaximized: false,
      panelMinimized: false,
    })
  })

  it('初始状态', () => {
    const s = useAppStore.getState()
    expect(s.selectedNodeId).toBeNull()
    expect(s.panelWidth).toBe(420)
    expect(s.panelMaximized).toBe(false)
    expect(s.panelMinimized).toBe(false)
    expect(s.editable).toBe(false)
  })

  it('setSelectedNodeId 更新 selectedNodeId', () => {
    useAppStore.getState().setSelectedNodeId('task-1')
    expect(useAppStore.getState().selectedNodeId).toBe('task-1')
    useAppStore.getState().setSelectedNodeId(null)
    expect(useAppStore.getState().selectedNodeId).toBeNull()
  })

  it('setPanelWidth 更新 panelWidth', () => {
    useAppStore.getState().setPanelWidth(560)
    expect(useAppStore.getState().panelWidth).toBe(560)
  })

  it('setPanelMaximized 切换 panelMaximized', () => {
    useAppStore.getState().setPanelMaximized(true)
    expect(useAppStore.getState().panelMaximized).toBe(true)
  })

  it('setPanelMinimized 切换 panelMinimized', () => {
    useAppStore.getState().setPanelMinimized(true)
    expect(useAppStore.getState().panelMinimized).toBe(true)
  })
})
