import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  useCreatePipeline,
  useRenamePipeline,
  useDeletePipeline,
  useCreateFolder,
  useRenameFolder,
  useDeleteFolder,
} from './pipelines';

const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock('./client', () => ({
  default: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
    put: vi.fn(),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

/** v3 (2026-09): 网页端流水线/文件夹 CRUD hooks 的 URL 与 payload 验证 */
describe('pipeline CRUD API hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('useCreatePipeline POST /by-file 并传递项目与内容', async () => {
    mockPost.mockResolvedValueOnce({ data: { status: 'ok', file: 'demo.yaml', definition_id: 'd1' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreatePipeline(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', file: 'demo.yaml', content: 'name: demo' });

    expect(mockPost).toHaveBeenCalledWith('/api/pipelines/by-file/p1', {
      file: 'demo.yaml',
      content: 'name: demo',
    });
  });

  it('useRenamePipeline PATCH /by-file 使用 new_file 字段', async () => {
    mockPatch.mockResolvedValueOnce({ data: { status: 'ok' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRenamePipeline(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', file: 'a.yaml', newFile: 'b.yaml' });

    expect(mockPatch).toHaveBeenCalledWith('/api/pipelines/by-file/p1', {
      file: 'a.yaml',
      new_file: 'b.yaml',
    });
  });

  it('useDeletePipeline DELETE /by-file 携带 file 查询参数', async () => {
    mockDelete.mockResolvedValueOnce({ data: { status: 'deleted' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDeletePipeline(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', file: 'a.yaml' });

    expect(mockDelete).toHaveBeenCalledWith('/api/pipelines/by-file/p1', {
      params: { file: 'a.yaml' },
    });
  });

  it('useCreateFolder POST /folders', async () => {
    mockPost.mockResolvedValueOnce({ data: { status: 'ok' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useCreateFolder(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', folder: 'debug/prod' });

    expect(mockPost).toHaveBeenCalledWith('/api/pipelines/folders/p1', { folder: 'debug/prod' });
  });

  it('useRenameFolder PATCH /folders 使用 new_folder 字段', async () => {
    mockPatch.mockResolvedValueOnce({ data: { status: 'ok' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useRenameFolder(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', folder: 'a', newFolder: 'b' });

    expect(mockPatch).toHaveBeenCalledWith('/api/pipelines/folders/p1', {
      folder: 'a',
      new_folder: 'b',
    });
  });

  it('useDeleteFolder DELETE /folders 携带 recursive 参数', async () => {
    mockDelete.mockResolvedValueOnce({ data: { status: 'deleted' } });
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useDeleteFolder(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', folder: 'debug', recursive: true });

    expect(mockDelete).toHaveBeenCalledWith('/api/pipelines/folders/p1', {
      params: { folder: 'debug', recursive: true },
    });
  });

  it('写操作成功后失效 pipelines 查询缓存', async () => {
    mockPost.mockResolvedValueOnce({ data: { status: 'ok', file: 'demo.yaml', definition_id: 'd1' } });
    const { queryClient, wrapper } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useCreatePipeline(), { wrapper });

    await result.current.mutateAsync({ projectId: 'p1', file: 'demo.yaml', content: 'name: demo' });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['pipelines'] });
  });
});
