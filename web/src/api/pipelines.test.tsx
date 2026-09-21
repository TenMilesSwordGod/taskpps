import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useSavePipelineById, useSavePipelineByFile } from './pipelines'

/**
 * v7 (2026-08): pipeline 保存 hook 的请求与缓存一致性测试。
 *
 * 为什么单测 hook 而不是只测页面：
 * 保存成功后需要让「流水线列表」等其它查询失效，否则用户返回列表
 * 仍会看到旧名称/旧校验状态（React Query 默认 staleTime 内不会重新拉取）。
 */

const mockPut = vi.fn()

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    put: (...args: unknown[]) => mockPut(...args),
  },
}))

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  return { qc, wrapper }
}

describe('pipeline 保存 hook：请求与缓存失效', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPut.mockResolvedValue({ data: { status: 'ok' } })
  })

  it('[happy] useSavePipelineById：PUT by-id 并失效详情缓存', async () => {
    const { qc, wrapper } = createWrapper()
    qc.setQueryData(['pipeline', 'def-1'], { name: 'old' })

    const { result } = renderHook(() => useSavePipelineById('def-1'), { wrapper })
    await act(async () => {
      await result.current.mutateAsync('name: new\n')
    })

    expect(mockPut).toHaveBeenCalledWith('/api/pipelines/by-id/def-1', { content: 'name: new\n' })
    expect(qc.getQueryState(['pipeline', 'def-1'])?.isInvalidated).toBe(true)
  })

  it('[P2] useSavePipelineById 成功后必须失效流水线列表缓存', async () => {
    const { qc, wrapper } = createWrapper()
    qc.setQueryData(['pipelines'], { items: [] })

    const { result } = renderHook(() => useSavePipelineById('def-1'), { wrapper })
    await act(async () => {
      await result.current.mutateAsync('name: renamed\n')
    })

    expect(qc.getQueryState(['pipelines'])?.isInvalidated).toBe(true)
  })

  it('[happy] useSavePipelineByFile：PUT by-file 并失效列表与文件缓存', async () => {
    const { qc, wrapper } = createWrapper()
    qc.setQueryData(['pipelines'], { items: [] })
    qc.setQueryData(['pipeline-file', 'proj-1', 'a.yaml'], { name: 'a' })

    const { result } = renderHook(() => useSavePipelineByFile('proj-1'), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ file: 'a.yaml', content: 'name: a\n' })
    })

    expect(mockPut).toHaveBeenCalledWith('/api/pipelines/by-file/proj-1', {
      file: 'a.yaml',
      content: 'name: a\n',
    })
    expect(qc.getQueryState(['pipelines'])?.isInvalidated).toBe(true)
    expect(qc.getQueryState(['pipeline-file', 'proj-1', 'a.yaml'])?.isInvalidated).toBe(true)
  })
})
