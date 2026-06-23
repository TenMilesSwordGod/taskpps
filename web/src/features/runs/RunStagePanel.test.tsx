import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RunStagePanel from './RunStagePanel';
import type { PipelineDetail, TaskRunResponse } from '@/types';

function makePipeline(overrides: Partial<PipelineDetail> = {}): PipelineDetail {
  return {
    name: 'demo',
    pipelines: [
      {
        name: 'build',
        depends_on: [],
        tasks: [
          { name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] },
          { name: 'test', command: 'make test', env: {}, retry: 0, depends_on: [] },
        ],
      },
      {
        name: 'deploy',
        depends_on: [],
        tasks: [{ name: 'push', command: 'deploy', env: {}, retry: 0, depends_on: [] }],
      },
    ],
    ...overrides,
  };
}

function makeTask(overrides: Partial<TaskRunResponse> = {}): TaskRunResponse {
  return {
    id: 't1',
    run_id: 'run-1',
    task_name: 'build.compile',
    subpipeline_name: 'build',
    task_type: 'command',
    status: 'success',
    exit_code: 0,
    error: null,
    log_path: '',
    started_at: null,
    finished_at: null,
    created_at: '',
    ...overrides,
  };
}

describe('<RunStagePanel />', () => {
  it('无流水线定义且无任务运行时不渲染', () => {
    const { container } = render(<RunStagePanel />);
    expect(container.firstChild).toBeNull();
  });

  it('按流水线定义顺序渲染所有任务节点，并显示 stage 名称', () => {
    const pipeline = makePipeline();
    const taskRuns: TaskRunResponse[] = [
      makeTask({ task_name: 'build.compile', subpipeline_name: 'build', status: 'success' }),
      makeTask({ task_name: 'build.test', subpipeline_name: 'build', status: 'running' }),
      makeTask({ task_name: 'deploy.push', subpipeline_name: 'deploy', status: 'pending' }),
    ];
    render(<RunStagePanel pipeline={pipeline} taskRuns={taskRuns} />);

    const nodes = screen.getAllByTestId('stage-node');
    expect(nodes).toHaveLength(3);
    expect(nodes[0]).toHaveAttribute('data-task-name', 'build.compile');
    expect(nodes[1]).toHaveAttribute('data-task-name', 'build.test');
    expect(nodes[2]).toHaveAttribute('data-task-name', 'deploy.push');

    expect(screen.getByText('build')).toBeInTheDocument();
    expect(screen.getByText('deploy')).toBeInTheDocument();
  });

  it('未匹配到运行记录的任务默认显示 pending 状态', () => {
    const pipeline = makePipeline();
    render(<RunStagePanel pipeline={pipeline} taskRuns={[]} />);

    const nodes = screen.getAllByTestId('stage-node');
    expect(nodes).toHaveLength(3);
    for (const node of nodes) {
      expect(node).toHaveAttribute('data-status', 'pending');
    }
  });

  it('任务状态颜色按运行结果正确设置，且圆点内包含图标', () => {
    const pipeline = makePipeline();
    const taskRuns: TaskRunResponse[] = [
      makeTask({ task_name: 'build.compile', subpipeline_name: 'build', status: 'success' }),
      makeTask({ task_name: 'build.test', subpipeline_name: 'build', status: 'failed' }),
      makeTask({ task_name: 'deploy.push', subpipeline_name: 'deploy', status: 'skipped' }),
    ];
    render(<RunStagePanel pipeline={pipeline} taskRuns={taskRuns} />);

    const nodes = screen.getAllByTestId('stage-node');
    expect(nodes[0]).toHaveAttribute('data-status', 'success');
    expect(nodes[1]).toHaveAttribute('data-status', 'failed');
    expect(nodes[2]).toHaveAttribute('data-status', 'skipped');

    for (const node of nodes) {
      expect(node.querySelector('svg')).toBeTruthy();
    }
  });

  it('运行中的任务图标带有旋转动画', () => {
    const pipeline = makePipeline();
    const taskRuns: TaskRunResponse[] = [
      makeTask({ task_name: 'build.compile', subpipeline_name: 'build', status: 'running' }),
    ];
    render(<RunStagePanel pipeline={pipeline} taskRuns={taskRuns} />);

    const node = screen.getAllByTestId('stage-node')[0];
    expect(node.querySelector('.animate-spin')).toBeTruthy();
  });

  it('顺序 stage 的任务节点水平排列', () => {
    const pipeline = makePipeline();
    render(<RunStagePanel pipeline={pipeline} taskRuns={[]} />);

    const tasksContainer = screen.getByTestId('stage-tasks-build');
    expect(tasksContainer).toHaveAttribute('data-stage-name', 'build');
    expect((tasksContainer as HTMLElement).style.flexDirection).toBe('row');
  });

  it('并行 stage 的任务节点垂直排列', () => {
    const pipeline = makePipeline({
      pipelines: [
        {
          name: 'test',
          config: { execution_strategy: 'parallel', env: {}, retry: 0, on_failure: 'stop' },
          depends_on: [],
          tasks: [
            { name: 'unit', command: 'unit', env: {}, retry: 0, depends_on: [] },
            { name: 'integration', command: 'integration', env: {}, retry: 0, depends_on: [] },
          ],
        },
      ],
    });
    render(<RunStagePanel pipeline={pipeline} taskRuns={[]} />);

    const tasksContainer = screen.getByTestId('stage-tasks-test');
    expect(tasksContainer).toHaveAttribute('data-stage-name', 'test');
    expect((tasksContainer as HTMLElement).style.flexDirection).toBe('column');
  });

  it('stage 之间用带箭头的连线连接', () => {
    const pipeline = makePipeline();
    render(<RunStagePanel pipeline={pipeline} taskRuns={[]} />);

    const lines = document.querySelectorAll('line');
    expect(lines.length).toBeGreaterThan(0);
  });

  it('运行记录中存在但流水线定义中不存在的任务追加为新 stage', () => {
    const pipeline = makePipeline();
    const taskRuns: TaskRunResponse[] = [
      makeTask({ task_name: 'build.compile', subpipeline_name: 'build', status: 'success' }),
      makeTask({ task_name: 'orphan.task', subpipeline_name: 'build', status: 'failed' }),
    ];
    render(<RunStagePanel pipeline={pipeline} taskRuns={taskRuns} />);

    const nodes = screen.getAllByTestId('stage-node');
    expect(nodes).toHaveLength(4);
    expect(nodes[3]).toHaveAttribute('data-task-name', 'orphan.task');
    expect(nodes[3]).toHaveAttribute('data-status', 'failed');
    expect(screen.getByText('orphan')).toBeInTheDocument();
  });
});
