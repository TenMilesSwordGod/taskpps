import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import LogViewer from './LogViewer';
import type { LogEntry } from './hooks/useSSELogs';

function makeLog(seq: number, taskName: string, content: string): LogEntry {
  return { seq, taskName, content, timestamp: Date.now() + seq };
}

const baseProps = {
  connected: true,
  autoScroll: false,
  onAutoScrollChange: vi.fn(),
  onClear: vi.fn(),
};

describe('<LogViewer /> Issue #71 - 任务颜色优化', () => {
  it('不同任务名分配不同颜色（避免 hash 碰撞）', () => {
    // 这两个任务名在旧 hash 算法下会碰撞到同一颜色
    const logs: LogEntry[] = [
      makeLog(1, 'Sync Automation code.list files', '[INFO] start'),
      makeLog(2, 'Sync Automation code.list files', '10.239.146.127'),
      makeLog(3, 'Automation Weekly Tests.AOSP', '[INFO] AgentExecutor'),
      makeLog(4, 'Automation Weekly Tests.AOSP', 'uv run run.py'),
    ];
    render(<LogViewer logs={logs} {...baseProps} />);

    // 找到两个任务名的 span（每个任务出现 2 次，取第一个即可）
    const syncSpans = screen.getAllByText('[Sync Automation code.list files]');
    const aospSpans = screen.getAllByText('[Automation Weekly Tests.AOSP]');

    const syncColor = (syncSpans[0] as HTMLElement).style.color;
    const aospColor = (aospSpans[0] as HTMLElement).style.color;

    // 两个不同任务必须有不同颜色
    expect(syncColor).toBeTruthy();
    expect(aospColor).toBeTruthy();
    expect(syncColor).not.toBe(aospColor);
  });

  it('同一任务名始终使用相同颜色', () => {
    const logs: LogEntry[] = [
      makeLog(1, 'TaskA', 'line 1'),
      makeLog(2, 'TaskB', 'line 2'),
      makeLog(3, 'TaskA', 'line 3'),
    ];
    render(<LogViewer logs={logs} {...baseProps} />);

    const aSpans = screen.getAllByText('[TaskA]');
    expect(aSpans.length).toBe(2);
    const color1 = (aSpans[0] as HTMLElement).style.color;
    const color2 = (aSpans[1] as HTMLElement).style.color;
    expect(color1).toBe(color2);
  });

  it('多个任务按首次出现顺序分配颜色，相邻不同色', () => {
    const logs: LogEntry[] = [
      makeLog(1, 'T1', 'a'),
      makeLog(2, 'T2', 'b'),
      makeLog(3, 'T3', 'c'),
      makeLog(4, 'T4', 'd'),
    ];
    render(<LogViewer logs={logs} {...baseProps} />);

    const colors = ['T1', 'T2', 'T3', 'T4'].map((name) => {
      const span = screen.getByText(`[${name}]`) as HTMLElement;
      return span.style.color;
    });

    // 相邻任务颜色不同
    for (let i = 0; i < colors.length - 1; i++) {
      expect(colors[i]).not.toBe(colors[i + 1]);
    }
  });
});
