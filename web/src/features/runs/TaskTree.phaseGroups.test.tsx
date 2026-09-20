import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TaskTree from './TaskTree';
import type { PipelineDetail } from '@/types';

const TS = '2026-09-12T15:13:12.466459+00:00';

/** 任务结束后后端会补发 SUB:SETUP 作用域标签（v2 2026-09） */
const CONSOLE_CONTENT = [
  `[SUB:sub1:SETUP] [${TS}] `,
  `[INFO] [${TS}] Starting SubPipeline 'sub1' with 1 tasks`,
  `[TASK:sub1.taskA:SETUP] [${TS}] `,
  `[INFO] [${TS}] Executing task 'sub1.taskA'`,
  `[TASK:sub1.taskA:TEARDOWN] [${TS}] `,
  `[INFO] [${TS}] Task 'sub1.taskA' finished with exit_code=0`,
  `[SUB:sub1:SETUP] [${TS}] `,
  `[DEBUG] [${TS}] SubPipeline 'sub1' level 2: []`,
].join('\n');

vi.mock('@/api/runs', () => ({
  useRunConsole: () => ({ data: { content: CONSOLE_CONTENT } }),
}));

const pipeline: PipelineDetail = {
  name: 'demo',
  pipelines: [
    {
      name: 'sub1',
      depends_on: [],
      tasks: [{ name: 'taskA', command: 'echo hello', env: {}, retry: 0, depends_on: [] }],
    },
  ],
};

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('<TaskTree /> phase 分组去重（v2 2026-09）', () => {
  it('后端重复声明的 SUB:SETUP 合并为同一个 phase 节点，不产生重复分组', () => {
    render(
      <Wrapper>
        <TaskTree pipeline={pipeline} onSelect={vi.fn()} debugVisible runId="r1" />
      </Wrapper>,
    );

    // "sub1 setup" 只应出现一次（重复标签合并到首次出现的组）
    expect(screen.getAllByText('sub1 setup')).toHaveLength(1);
  });
});
