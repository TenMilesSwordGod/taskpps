import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PipelineBreadcrumb from './PipelineBreadcrumb'

/** mock apiClient — 控制 useQuery 返回的数据 */
const mockGet = vi.fn()
vi.mock('@/api/client', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))

/** mock useProject — 简化测试，直接控制返回值 */
const mockUseProjectResult = vi.fn()
vi.mock('@/api/projects', () => ({
  useProject: () => mockUseProjectResult(),
}))

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/pipelines/proj-1/def-1']}>
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('<PipelineBreadcrumb />', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockUseProjectResult.mockReset()
  })

  it('加载项目名时显示骨架屏', () => {
    mockUseProjectResult.mockReturnValue({
      data: undefined,
      isLoading: true,
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          definitionId="def-1"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByTestId('breadcrumb-loading')).toBeInTheDocument()
  })

  it('加载完成后显示项目名和流水线名', () => {
    mockUseProjectResult.mockReturnValue({
      data: { id: 'proj-1', name: '测试项目' },
      isLoading: false,
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          definitionId="def-1"
          pipelineName="流水线A"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByText('测试项目')).toBeInTheDocument()
    expect(screen.getByText('流水线A')).toBeInTheDocument()
    expect(screen.getByText('流水线')).toBeInTheDocument()
  })

  it('文件模式显示文件路径', () => {
    mockUseProjectResult.mockReturnValue({
      data: { id: 'proj-1', name: '测试项目' },
      isLoading: false,
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          isFileMode={true}
          filePath="path/to/file.yaml"
        />
      </Wrapper>,
    )

    expect(screen.getByText('path/to/file.yaml')).toBeInTheDocument()
  })

  it('props 传入 projectName 时优先使用，不触发 API', () => {
    mockUseProjectResult.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          projectName="优先项目名"
          definitionId="def-1"
          pipelineName="优先流水线名"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByText('优先项目名')).toBeInTheDocument()
    expect(screen.getByText('优先流水线名')).toBeInTheDocument()
  })

  it('无 pipelineName 时 fallback 显示 definitionId', () => {
    mockUseProjectResult.mockReturnValue({
      data: { id: 'proj-1', name: '项目X' },
      isLoading: false,
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          definitionId="def-123"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByText('项目X')).toBeInTheDocument()
    expect(screen.getByText('def-123')).toBeInTheDocument()
  })

  it('无 projectName 且 API 未返回时 fallback 显示 projectId', () => {
    mockUseProjectResult.mockReturnValue({
      data: undefined,
      isLoading: false,
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          definitionId="def-1"
          pipelineName="流A"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByText('proj-1')).toBeInTheDocument()
  })

  it('项目名悬浮触发 onPopoverOpen 并加载项目列表', async () => {
    mockUseProjectResult.mockReturnValue({
      data: { id: 'proj-1', name: '测试项目' },
      isLoading: false,
    })

    // mock apiClient.get('/api/projects/') 返回项目列表
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/api/projects/') {
        return {
          data: [
            { id: 'proj-1', name: '项目A', workdir: '/a', registered_at: '', last_used_at: null, active: true },
            { id: 'proj-2', name: '项目B', workdir: '/b', registered_at: '', last_used_at: null, active: true },
          ],
        }
      }
      return { data: [] }
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          definitionId="def-1"
          pipelineName="流水线A"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByText('测试项目')).toBeInTheDocument()

    // 悬浮项目名触发浮窗 + API 请求
    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-测试项目'))

    // 等待项目列表加载
    await waitFor(
      () => {
        expect(screen.getByTestId('popover-option-proj-2')).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
  })

  it('流水线名悬浮触发 onPopoverOpen 并加载流水线列表', async () => {
    mockUseProjectResult.mockReturnValue({
      data: { id: 'proj-1', name: '测试项目' },
      isLoading: false,
    })

    mockGet.mockImplementation(async (url: string) => {
      if (url === '/api/pipelines/') {
        return {
          data: {
            items: [
              {
                id: 'def-1',
                name: '流水线A',
                file: 'a.yaml',
                folder: '',
                project_id: 'proj-1',
                project_name: '项目A',
                valid: true,
                task_count: 3,
                subpipeline_count: 1,
                last_run: null,
                success_rate: 1,
                recent_runs: [],
                validation_error: null,
              },
              {
                id: 'def-2',
                name: '流水线B',
                file: 'b.yaml',
                folder: 'debug',
                project_id: 'proj-1',
                project_name: '项目A',
                valid: true,
                task_count: 2,
                subpipeline_count: 0,
                last_run: null,
                success_rate: 0.8,
                recent_runs: [],
                validation_error: null,
              },
            ],
          },
        }
      }
      return { data: [] }
    })

    render(
      <Wrapper>
        <PipelineBreadcrumb
          projectId="proj-1"
          definitionId="def-1"
          pipelineName="流水线A"
          isFileMode={false}
        />
      </Wrapper>,
    )

    expect(screen.getByText('流水线A')).toBeInTheDocument()

    fireEvent.mouseEnter(screen.getByTestId('crumb-hover-流水线A'))

    await waitFor(
      () => {
        expect(screen.getByTestId('popover-option-def-2')).toBeInTheDocument()
      },
      { timeout: 2000 },
    )

    // folder 前缀
    expect(screen.getByTestId('popover-option-def-2').textContent).toContain('debug/流水线B')
  })
})
