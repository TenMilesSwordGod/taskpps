import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProvider } from './test-utils';
import EditorSubPipelineNode from '../nodes/EditorSubPipelineNode';
import EditorTaskNode from '../nodes/EditorTaskNode';
import EditorPostParentNode from '../nodes/EditorPostParentNode';
import EditorPostChildNode from '../nodes/EditorPostChildNode';
import EditorStartEndNode from '../nodes/EditorStartEndNode';
import EditorPipelineNode from '../nodes/EditorPipelineNode';
import type { TaskYAML } from '@/types';

/**
 * 容器嵌套规则校验测试
 * 验证:
 *   1. 各节点类型渲染结构正确（handle 端口、标签、样式）
 *   2. SubPipeline/Task 容器有 in/out/post 三端口
 *   3. Post 父容器仅有 in 端口（不可再嵌套子容器端口）
 *   4. Post 子容器具有正确的 variant 样式
 *   5. Start/End 哨兵节点结构
 *   6. Pipeline 根容器结构
 */

function makeTask(taskName: string, command?: string): TaskYAML {
  return { name: taskName, command: command || 'echo hi', env: {}, retry: 0, depends_on: [] };
}

describe('SubPipeline 容器节点', () => {
  it('渲染时显示名称和执行策略角标', () => {
    const { unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build', executionStrategy: 'sequential' }} />,
    );
    expect(screen.getByText('build')).toBeInTheDocument();
    expect(screen.getByText('SEQ')).toBeInTheDocument();
    unmount();
  });

  it('parallel 策略显示 PAR(N) 角标', () => {
    const { unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'par', executionStrategy: 'parallel', maxConcurrentTasks: 3 }} />,
    );
    expect(screen.getByText('PAR(3)')).toBeInTheDocument();
    unmount();
  });

  it('有 in/out/post 三端口 handle', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).toContain('out');
    expect(handleIds).toContain('post');
    expect(handles.length).toBe(3);
    unmount();
  });

  // v6/v7 (2026-08): 选中态统一为品牌橙 accent（#FF6D5A → rgb(255, 109, 90)）
  it('选中状态时显示品牌橙高亮光环', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} selected={true} />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    expect(style).toContain('255, 109, 90');
    expect(style).toContain('box-shadow');
    unmount();
  });
});

describe('Task 容器节点', () => {
  it('渲染时显示任务名称和类型图标', () => {
    const { unmount } = renderWithProvider(
      <EditorTaskNode data={{ task: makeTask('compile'), taskType: 'command' }} />,
    );
    expect(screen.getByText('compile')).toBeInTheDocument();
    unmount();
  });

  it('有 in/out/post 三端口 handle', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode data={{ task: makeTask('test') }} />,
    );
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).toContain('out');
    expect(handleIds).toContain('post');
    expect(handles.length).toBe(3);
    unmount();
  });

  // v7 (2026-08): when 徽章带 "when: " 前缀并截断至 22 字符
  it('when 条件存在时显示条件徽章（when: 前缀）', () => {
    const { unmount } = renderWithProvider(
      <EditorTaskNode data={{ task: { ...makeTask('conditional'), when: '${BRANCH} == main' }, taskType: 'command' }} />,
    );
    expect(screen.getByText(/when: \$\{BRANCH\}/)).toBeInTheDocument();
    unmount();
  });
});

describe('Post 父容器节点', () => {
  it('仅有 in 端口（无 out/post）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).not.toContain('out');
    expect(handleIds).not.toContain('post');
    expect(handles.length).toBe(1);
    unmount();
  });

  it('渲染时显示标题和红色图标', () => {
    const { unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'deploy Post' }} />,
    );
    expect(screen.getByText('deploy Post')).toBeInTheDocument();
    unmount();
  });
});

describe('Post 子容器节点', () => {
  it('仅有 in 端口', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostChildNode data={{ task: makeTask('notify'), postVariant: 'on_fail' }} />,
    );
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).not.toContain('out');
    expect(handles.length).toBe(1);
    unmount();
  });

  it('on_fail variant 显示"失败时"标签和红色强调条', () => {
    const { unmount } = renderWithProvider(
      <EditorPostChildNode data={{ task: makeTask('alert'), postVariant: 'on_fail' }} />,
    );
    expect(screen.getByText('失败时')).toBeInTheDocument();
    expect(screen.getByText('alert')).toBeInTheDocument();
    unmount();
  });

  it('on_success variant 显示"成功时"标签', () => {
    const { unmount } = renderWithProvider(
      <EditorPostChildNode data={{ task: makeTask('tag'), postVariant: 'on_success' }} />,
    );
    expect(screen.getByText('成功时')).toBeInTheDocument();
    unmount();
  });

  it('always variant 显示"始终"标签', () => {
    const { unmount } = renderWithProvider(
      <EditorPostChildNode data={{ task: makeTask('cleanup'), postVariant: 'always' }} />,
    );
    expect(screen.getByText('始终')).toBeInTheDocument();
    unmount();
  });
});

describe('Start/End 哨兵节点', () => {
  // v7 (2026-08): 哨兵圆形节点不再渲染 START/END 文本（图标语义 ▶/■），
  // handle id 契约不变（out/in），方位从右/左改为下/上
  it('Start 节点仅有 out 端口（底部）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorStartEndNode data={{ variant: 'start' }} />,
    );
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('out');
    expect(handleIds).not.toContain('in');
    unmount();
  });

  it('End 节点仅有 in 端口（顶部）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorStartEndNode data={{ variant: 'end' }} />,
    );
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).not.toContain('out');
    unmount();
  });
});

describe('Pipeline 根容器节点', () => {
  // v4 (2026-07): Bug#45 — Pipeline 新增 in 端口用于连接 Start
  it('有 in、out 和 post 端口', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPipelineNode data={{ label: 'MyPipeline' }} />,
    );
    expect(screen.getByText('MyPipeline')).toBeInTheDocument();
    const handles = container.querySelectorAll('[data-handleid]');
    const handleIds = Array.from(handles).map(h => h.getAttribute('data-handleid'));
    expect(handleIds).toContain('in');
    expect(handleIds).toContain('out');
    expect(handleIds).toContain('post');
    unmount();
  });
});
