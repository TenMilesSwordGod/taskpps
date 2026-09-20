import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route, Link } from 'react-router-dom'
import { App as AntdApp, message } from 'antd'
import { EditorView } from '@codemirror/view'
import { load as parseYamlText } from 'js-yaml'
import { forwardRef, useImperativeHandle } from 'react'
import type { ReactNode } from 'react'
import type { PipelineDetail } from '@/types'

/**
 * v7 (2026-08): 「前端编辑 YAML → 保存到后端」全链路加固测试。
 *
 * 覆盖矩阵（不只 happy path）：
 *   by-id  : 编辑→保存成功 / 保存失败 / Ctrl+S / refetch 不覆盖草稿
 *   by-file: 自动加载 raw_content→保存 / 放弃并关闭 / 空文件保存
 *   时序   : debounce(300ms) 与保存竞态（最后输入是否落盘）
 *   路由   : 编辑器开着草稿时切换流水线（是否串稿）
 *   离页   : dirty 草稿的 beforeunload 守卫
 *   保存后 : 重新打开是否保留用户注释/格式
 *
 * 本文件 mock 的是网络层（@/api/client），因此 @/api/pipelines 的真实
 * React Query hooks 会参与执行，能捕获「缓存失效 / 请求体 / 请求地址」类缺陷。
 * 编辑器使用真实 CodeMirror（通过 EditorView.findFromDOM 注入文档变更），
 * 因此能捕获 debounce 与保存的时序缺陷。
 *
 * v7 修复前这些 [P1]/[P2] 用例全部为 RED，对应缺陷：
 *   P1 debounce 窗口内保存丢最后输入；P1 切换流水线串稿；P2 文件模式放弃不还原；
 *   P2 空内容保存静默无响应；P2 重开吞注释；P2 保存中可重复提交；
 *   P2 YAML 草稿无 beforeunload 守卫；P2 by-id 保存不失效列表缓存。
 */

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
  },
  // useIsAdmin → @/api/auth 会引用这些命名导出
  getToken: () => 'test-token',
  setToken: vi.fn(),
  clearToken: vi.fn(),
  TOKEN_KEY: 'taskpps_token',
}))

// 变量悬浮数据源与权限判断不属于保存链路，用空数据隔离
vi.mock('@/hooks/useIsAdmin', () => ({ useIsAdmin: () => false }))
vi.mock('@/api/agents', () => ({ useAgentsWithConfig: () => ({ data: [] }) }))
vi.mock('@/api/credentials', () => ({ useCredentials: () => ({ data: [] }) }))

// 只 mock 重渲染成本高的展示型子组件，保留真实 YamlEditor 与真实 API hooks
vi.mock('@/features/pipelines/workflow/WorkflowEditor', () => ({
  default: forwardRef((_props: Record<string, unknown>, ref) => {
    useImperativeHandle(ref, () => ({ deleteNode: () => {}, isDirty: false }))
    return <div data-testid="workflow-editor" />
  }),
  WorkflowEditorRef: null,
}))
vi.mock('@/features/pipelines/workflow/NodePalette', () => ({ default: () => null }))
vi.mock('@/features/pipelines/workflow/PropertyPanel', () => ({ default: () => null }))
vi.mock('@/components/PipelineBreadcrumb', () => ({ default: () => <div /> }))
vi.mock('@/components/TriggerRunModal', () => ({ default: () => <div /> }))
vi.mock('@/features/pipelines/HelpPanel', () => ({ HelpPanel: () => <div /> }))

const PipelineDetailPage = (await import('@/features/pipelines/PipelineDetailPage')).default

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T

const PIPELINE_A: PipelineDetail = {
  name: 'pipe-a',
  tasks: [{ name: 'task-a', command: 'echo a', env: {}, retry: 0, depends_on: [] }],
}
const PIPELINE_B: PipelineDetail = {
  name: 'pipe-b',
  tasks: [{ name: 'task-b', command: 'echo b', env: {}, retry: 0, depends_on: [] }],
}

const FILE_BROKEN = {
  name: 'broken',
  file: 'broken.yaml',
  raw_content: 'name: broken\n  bad_indent: yes\n',
}
const FILE_EMPTY = { name: 'empty', file: 'empty.yaml', raw_content: '' }

// 有状态的服务端替身：PUT 保存后，后续 GET 返回保存后的内容。
// 这样「保存→refetch→重开编辑器」的用例才符合真实后端行为，
// 而不是永远返回静态旧数据（假绿）。
let serverPipelines: Record<string, PipelineDetail>
let serverFiles: Record<string, typeof FILE_BROKEN>

function installDefaultApiMocks() {
  serverPipelines = { 'def-A': clone(PIPELINE_A), 'def-B': clone(PIPELINE_B) }
  serverFiles = { 'broken.yaml': clone(FILE_BROKEN), 'empty.yaml': clone(FILE_EMPTY) }

  mockGet.mockImplementation((url: string, config?: { params?: { file?: string } }) => {
    if (url.startsWith('/api/pipelines/by-id/')) {
      const id = decodeURIComponent(url.split('/').pop()!)
      const found = serverPipelines[id]
      if (!found) return Promise.reject(new Error(`unknown definition: ${id}`))
      return Promise.resolve({ data: clone(found) })
    }
    if (url === '/api/pipelines/by-file/proj-1') {
      const file = config?.params?.file ?? ''
      const found = serverFiles[file]
      if (!found) return Promise.reject(new Error(`unknown file: ${file}`))
      return Promise.resolve({ data: clone(found) })
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })

  mockPut.mockImplementation((url: string, body: { content: string; file?: string }) => {
    if (url.startsWith('/api/pipelines/by-id/')) {
      const id = decodeURIComponent(url.split('/').pop()!)
      const parsed = parseYamlText(body.content)
      if (!parsed || typeof parsed !== 'object') {
        return Promise.reject(new Error('Invalid YAML'))
      }
      serverPipelines[id] = parsed as PipelineDetail
      return Promise.resolve({ data: { status: 'ok' } })
    }
    if (url === '/api/pipelines/by-file/proj-1' && body.file) {
      serverFiles[body.file] = { ...serverFiles[body.file], raw_content: body.content }
      return Promise.resolve({ data: { status: 'ok' } })
    }
    return Promise.reject(new Error(`unexpected PUT ${url}`))
  })
}

function renderPage(options: { entry?: string; extra?: ReactNode } = {}) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: Infinity },
      mutations: { retry: false },
    },
  })
  const result = render(
    <QueryClientProvider client={qc}>
      <AntdApp>
        <MemoryRouter initialEntries={[options.entry ?? '/pipelines/proj-1/def-A']}>
          <Routes>
            <Route path="/pipelines/:projectId/_file_/*" element={<PipelineDetailPage />} />
            <Route path="/pipelines/:projectId/:definitionId" element={<PipelineDetailPage />} />
          </Routes>
          {options.extra}
        </MemoryRouter>
      </AntdApp>
    </QueryClientProvider>,
  )
  return { qc, ...result }
}

const editorEl = () => document.querySelector('.cm-content') as HTMLElement | null

async function openEditor() {
  // 页面初始可能仍在加载流水线（Spin），先等工具栏按钮出现
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /YAML 编辑器/ })).toBeInTheDocument(),
  )
  fireEvent.click(screen.getByRole('button', { name: /YAML 编辑器/ }))
  await waitFor(() => expect(editorEl()).toBeTruthy())
}

/** 通过 CodeMirror 的 EditorView 注入文档变更，等价于用户敲键盘产生的 transaction */
function typeInEditor(text: string) {
  const el = editorEl()
  if (!el) throw new Error('YAML 编辑器未挂载')
  const view = EditorView.findFromDOM(el)
  if (!view) throw new Error('CodeMirror EditorView 未找到')
  act(() => {
    view.dispatch({ changes: { from: view.state.doc.length, insert: text } })
  })
}

/** 等待 onChange 的 300ms debounce 落定 */
async function flushDebounce() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 350))
  })
}

// 按钮可访问名包含图标 aria-label（如 "save 保存"），用正则匹配
const clickSave = () => fireEvent.click(screen.getByRole('button', { name: /保存/ }))
const clickCloseEditor = () => fireEvent.click(screen.getByRole('button', { name: /关闭编辑器/ }))

describe('YAML 编辑→保存后端（全链路）', () => {
  let successSpy: ReturnType<typeof vi.spyOn>
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    installDefaultApiMocks()
    successSpy = vi.spyOn(message, 'success').mockImplementation((() => {}) as never)
    errorSpy = vi.spyOn(message, 'error').mockImplementation((() => {}) as never)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    cleanup()
    document
      .querySelectorAll('.ant-modal-root, .ant-modal-mask, .ant-modal-wrap, .ant-message')
      .forEach((el) => el.remove())
  })

  // ---------------------------------------------------------------- by-id

  it('[happy] by-id：编辑后保存 → PUT 到当前 definition，请求体为最新内容，成功后 dirty 清零', async () => {
    renderPage()
    await openEditor()
    expect(editorEl()!.textContent).toContain('pipe-a')

    typeInEditor('\n# note-1\n')
    await flushDebounce()
    clickSave()

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1))
    expect(mockPut.mock.calls[0][0]).toBe('/api/pipelines/by-id/def-A')
    expect(mockPut.mock.calls[0][1]).toEqual({ content: expect.stringContaining('# note-1') })
    await waitFor(() => expect(successSpy).toHaveBeenCalledWith('已保存'))

    // dirty 已清零：关闭不再弹「放弃未保存」确认
    clickCloseEditor()
    await waitFor(() => expect(editorEl()).toBeNull())
    expect(screen.queryByText(/关闭编辑器将丢失未保存的内容/)).toBeNull()
  })

  it('[happy] by-id：保存失败显示后端 detail，草稿保留（关闭仍需确认）', async () => {
    mockPut.mockRejectedValueOnce(new Error('Invalid YAML: mapping values are not allowed here'))
    renderPage()
    await openEditor()
    typeInEditor('\n# note-2\n')
    await flushDebounce()
    clickSave()

    await waitFor(() =>
      expect(errorSpy).toHaveBeenCalledWith(
        '保存失败: Invalid YAML: mapping values are not allowed here',
      ),
    )

    clickCloseEditor()
    await waitFor(() =>
      expect(screen.getByText(/关闭编辑器将丢失未保存的内容/)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /继续编辑/ }))
    await waitFor(() => expect(document.querySelector('.ant-modal-confirm')).toBeNull())
    expect(editorEl()!.textContent).toContain('# note-2')
  })

  it('[happy] by-id：Ctrl+S 保存最新内容', async () => {
    renderPage()
    await openEditor()
    typeInEditor('\n# via-ctrl-s\n')
    await flushDebounce()

    fireEvent.keyDown(editorEl()!, { key: 's', code: 'KeyS', ctrlKey: true })

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1))
    expect(mockPut.mock.calls[0][1].content).toContain('# via-ctrl-s')
  })

  it('[happy] by-id：外部 refetch 时不覆盖 dirty 草稿', async () => {
    const { qc } = renderPage()
    await openEditor()
    typeInEditor('\n# draft-kept\n')
    await flushDebounce()

    await act(async () => {
      await qc.invalidateQueries({ queryKey: ['pipeline', 'def-A'] })
    })

    expect(editorEl()!.textContent).toContain('# draft-kept')
  })

  // ---------------------------------------------------- P1：debounce 时序

  it('[P1] debounce 窗口内点保存：请求体必须包含刚敲入的内容', async () => {
    renderPage()
    await openEditor()

    // 模拟「快速输入后立刻按保存」：不等待 300ms debounce
    typeInEditor('\n# fast-typing\n')
    clickSave()

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1))
    expect(mockPut.mock.calls[0][1].content).toContain('# fast-typing')
  })

  it('[P1] debounce 窗口内 Ctrl+S：请求体必须包含刚敲入的内容', async () => {
    renderPage()
    await openEditor()

    typeInEditor('\n# ctrl-s-race\n')
    fireEvent.keyDown(editorEl()!, { key: 's', code: 'KeyS', ctrlKey: true })

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1))
    expect(mockPut.mock.calls[0][1].content).toContain('# ctrl-s-race')
  })

  // -------------------------------------------------- P1：跨流水线串稿

  it('[P1] 草稿状态下切换流水线：编辑器必须切到新流水线，保存不得把 A 内容写入 B', async () => {
    renderPage({ extra: <Link to="/pipelines/proj-1/def-B">switch-to-b</Link> })
    await openEditor()
    expect(editorEl()!.textContent).toContain('pipe-a')

    typeInEditor('\n# from-pipe-a\n')
    await flushDebounce()

    fireEvent.click(screen.getByText('switch-to-b'))
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith('/api/pipelines/by-id/def-B', expect.anything()),
    )

    // 切换后编辑器应自动切到 B 的内容（修复前会残留 A 的草稿）
    await waitFor(() => expect(editorEl()!.textContent).toContain('pipe-b'))

    // 保存必须写向 B 且内容为 B，而不是把 A 的内容写入 B
    clickSave()
    await waitFor(() => expect(mockPut).toHaveBeenCalled())
    expect(mockPut.mock.calls[0][0]).toBe('/api/pipelines/by-id/def-B')
    expect(mockPut.mock.calls[0][1].content).toContain('pipe-b')
  })

  // ------------------------------------------------------------ by-file

  it('[happy] by-file：自动加载 raw_content，编辑后保存 PUT 到 by-file（携带 file 路径）', async () => {
    renderPage({ entry: '/pipelines/proj-1/_file_/broken.yaml' })
    await waitFor(() => expect(editorEl()!.textContent).toContain('bad_indent'))

    typeInEditor('\n# fix-attempt\n')
    await flushDebounce()
    clickSave()

    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1))
    expect(mockPut.mock.calls[0][0]).toBe('/api/pipelines/by-file/proj-1')
    expect(mockPut.mock.calls[0][1]).toEqual({
      file: 'broken.yaml',
      content: expect.stringContaining('# fix-attempt'),
    })
    await waitFor(() => expect(successSpy).toHaveBeenCalledWith('已保存'))
  })

  it('[P2] by-file：「放弃并关闭」必须还原磁盘原文', async () => {
    renderPage({ entry: '/pipelines/proj-1/_file_/broken.yaml' })
    await waitFor(() => expect(editorEl()!.textContent).toContain('bad_indent'))

    typeInEditor('\n# discard-me\n')
    await flushDebounce()

    clickCloseEditor()
    await waitFor(() =>
      expect(screen.getByText(/关闭编辑器将丢失未保存的内容/)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByRole('button', { name: /放弃并关闭/ }))
    await waitFor(() => expect(editorEl()).toBeNull())

    await openEditor()
    expect(editorEl()!.textContent).not.toContain('# discard-me')
  })

  it('[P2] by-file：空文件点击保存必须给出明确反馈', async () => {
    renderPage({ entry: '/pipelines/proj-1/_file_/empty.yaml' })
    await waitFor(() => expect(editorEl()).toBeTruthy())

    clickSave()

    await waitFor(() => expect(errorSpy).toHaveBeenCalled())
    expect(mockPut).not.toHaveBeenCalled()
  })

  // ---------------------------------------------------- P2：保存后状态

  it('[P1] 打开编辑器必须展示磁盘原文（注释/格式不丢）', async () => {
    const raw =
      'name: pipe-a\n' +
      '# 关键注释：这段不能丢\n' +
      'tasks:\n' +
      '  - name: task-a\n' +
      '    command: echo a\n'
    const defaultGet = mockGet.getMockImplementation()!
    mockGet.mockImplementation((url: string, config?: { params?: { file?: string } }) => {
      if (url === '/api/pipelines/by-id/def-A') {
        return Promise.resolve({ data: { ...clone(PIPELINE_A), raw_content: raw } })
      }
      return defaultGet(url, config)
    })

    renderPage()
    await openEditor()

    expect(editorEl()!.textContent).toContain('# 关键注释：这段不能丢')
  })

  it('[P2] 保存成功后重新打开编辑器必须保留用户注释', async () => {
    renderPage()
    await openEditor()

    // 同时改结构和注释：服务端解析后 pipeline 内容变化，refetch 会拿到新数据源
    typeInEditor('\n  - name: task-new\n    command: echo new\n# keep-this-comment\n')
    await flushDebounce()
    clickSave()
    await waitFor(() => expect(successSpy).toHaveBeenCalledWith('已保存'))

    // 等待保存成功后 invalidate 触发的 refetch 完成（mock 每次返回新对象）
    await waitFor(() =>
      expect(
        mockGet.mock.calls.filter((c) => c[0] === '/api/pipelines/by-id/def-A').length,
      ).toBeGreaterThanOrEqual(2),
    )

    clickCloseEditor()
    await waitFor(() => expect(editorEl()).toBeNull())
    await openEditor()
    expect(editorEl()!.textContent).toContain('# keep-this-comment')
  })

  it('[P2] 保存中重复触发（Ctrl+S）不得发送第二次请求', async () => {
    let resolvePut!: (v: unknown) => void
    mockPut.mockImplementationOnce(
      () => new Promise((resolve) => { resolvePut = resolve }),
    )
    renderPage()
    await openEditor()
    typeInEditor('\n# slow-save\n')
    await flushDebounce()

    clickSave()
    await waitFor(() => expect(mockPut).toHaveBeenCalledTimes(1))

    // 第一次请求仍在飞行中，再按 Ctrl+S
    fireEvent.keyDown(editorEl()!, { key: 's', code: 'KeyS', ctrlKey: true })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    expect(mockPut).toHaveBeenCalledTimes(1)
    resolvePut({ data: { status: 'ok' } })
  })

  // ------------------------------------------------------ P2：离页守卫

  it('[P2] 有未保存 YAML 草稿时关闭/刷新页面必须有 beforeunload 守卫', async () => {
    renderPage()
    await openEditor()
    typeInEditor('\n# unsaved\n')
    await flushDebounce()

    const event = new Event('beforeunload', { cancelable: true })
    const notPrevented = window.dispatchEvent(event)

    expect(notPrevented).toBe(false)
  })
})
