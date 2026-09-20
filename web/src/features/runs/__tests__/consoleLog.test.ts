import { describe, it, expect } from 'vitest';
import {
  parsePhaseLogEntries,
  mergePhaseAndTaskLogs,
  tokenizeConsoleLog,
} from '../consoleLog';
import type { LogEntry } from '../hooks/useSSELogs';

const TS = '2026-09-12T15:13:12.466459+00:00';

function makeLog(seq: number, taskName: string, content: string, timestamp = seq): LogEntry {
  return { seq, taskName, content, timestamp };
}

/** 模拟后端 console.log：SETUP 标签 → 分隔线/信息 → TEARDOWN 标签，
 *  任务结束后补发 SUB:SETUP 作用域标签（v2 2026-09 起） */
const CONSOLE_LOG = [
  '[PIPELINE:SETUP]',
  '[SYSTEM] Run ID: r1',
  `[SUB:test:SETUP] [${TS}] `,
  `[INFO] [${TS}] Starting SubPipeline 'test' with 2 tasks`,
  `[DEBUG] [${TS}] SubPipeline 'test' level 1: ['hello']`,
  `[TASK:test.hello:SETUP] [${TS}] `,
  '--------------------------------------------------------------------------------',
  '-                            [task] test.hello start                            ',
  '--------------------------------------------------------------------------------',
  `[INFO] [${TS}] Executing task 'test.hello' (type: command, timeout: default)`,
  `[CMD] [${TS}]   command: echo "Hello from taskpps"`,
  `[DEBUG] [${TS}] Task 'test.hello' result: exit_code=0, success=True`,
  `[TASK:test.hello:TEARDOWN] [${TS}] `,
  `[INFO] [${TS}] Task 'test.hello' finished with exit_code=0`,
  `[SUCCESS] [${TS}] Task 'test.hello' completed with exit code: 0`,
  `[SUB:test:SETUP] [${TS}] `,
  `[DEBUG] [${TS}] SubPipeline 'test' level 2: ['test']`,
  `[DEBUG] [${TS}] Executing 1 tasks sequentially`,
  `[TASK:test.test:SETUP] [${TS}] `,
  '--------------------------------------------------------------------------------',
  '-                            [task] test.test start                             ',
  '--------------------------------------------------------------------------------',
  `[WARN] [${TS}] Task 'test.test' has an empty command`,
  '[PIPELINE:TEARDOWN]',
  `[SYSTEM] End Time: ${TS}`,
].join('\n');

describe('parsePhaseLogEntries', () => {
  it('任务结束后的层级/汇总日志归属子流水线，而非上一个任务', () => {
    const entries = parsePhaseLogEntries(CONSOLE_LOG);
    const level2 = entries.find((e) => e.content.includes("SubPipeline 'test' level 2"));
    expect(level2?.phase).toBe('test');

    const level1 = entries.find((e) => e.content.includes("SubPipeline 'test' level 1"));
    expect(level1?.phase).toBe('test');
  });

  it('SETUP 标签之后的分隔线归属对应任务', () => {
    const entries = parsePhaseLogEntries(CONSOLE_LOG);
    const helloStart = entries.find((e) => e.content.includes('[task] test.hello start'));
    const testStart = entries.find((e) => e.content.includes('[task] test.test start'));
    expect(helloStart?.phase).toBe('test.hello');
    expect(testStart?.phase).toBe('test.test');
  });

  it('任务生命周期行保留在任务作用域内', () => {
    const entries = parsePhaseLogEntries(CONSOLE_LOG);
    const finished = entries.find((e) => e.content.includes("Task 'test.hello' finished"));
    expect(finished?.phase).toBe('test.hello');
    const completed = entries.find((e) => e.content.includes("Task 'test.hello' completed"));
    expect(completed?.phase).toBe('test.hello');
  });

  it('pipeline 结束段归属 pipeline', () => {
    const entries = parsePhaseLogEntries(CONSOLE_LOG);
    const endTime = entries.find((e) => e.content.includes('End Time:'));
    expect(endTime?.phase).toBe('pipeline');
  });

  it('从行内解析服务端时间戳，标签行时间戳可被后续无时间戳行继承', () => {
    const entries = parsePhaseLogEntries(CONSOLE_LOG);
    const level2 = entries.find((e) => e.content.includes("SubPipeline 'test' level 2"));
    expect(level2?.timestamp).toBe(Date.parse(TS));
    // 分隔线没有自己的时间戳，继承上一条标签/日志的时间戳而不是 0
    const startSep = entries.find((e) => e.content.includes('[task] test.hello start'));
    expect(startSep?.timestamp).toBe(Date.parse(TS));
  });

  it('tokenizeConsoleLog 保留标签 token 用于树分组', () => {
    const tags = tokenizeConsoleLog(CONSOLE_LOG).filter((t) => t.kind === 'tag');
    expect(tags.map((t) => (t.kind === 'tag' ? `${t.tag.scope}:${t.tag.name}:${t.tag.phase}` : ''))).toEqual([
      'pipeline:pipeline:setup',
      'sub:test:setup',
      'task:test.hello:setup',
      'task:test.hello:teardown',
      'sub:test:setup',
      'task:test.test:setup',
      'pipeline:pipeline:teardown',
    ]);
  });
});

describe('mergePhaseAndTaskLogs', () => {
  const phaseLogs: LogEntry[] = [
    makeLog(1, '__phase__test.hello', `[INFO] [${TS}] Executing task 'test.hello'`),
    makeLog(2, '__phase__test.hello', `[CMD] [${TS}]   command: echo "Hello from taskpps"`),
    makeLog(3, '__phase__test.hello', `[DEBUG] [${TS}] Task 'test.hello' result: exit_code=0`),
    makeLog(4, '__phase__test.hello', `[INFO] [${TS}] Task 'test.hello' finished`),
    makeLog(5, '__phase__test', `[DEBUG] [${TS}] SubPipeline 'test' level 2`),
    makeLog(6, '__phase__test.test', `[WARN] Task 'test.test' has an empty command`),
  ];

  it('任务日志插入到本任务 [CMD] 行之后、结果行之前', () => {
    const taskLogs = [
      makeLog(101, 'test.hello', 'Hello from taskpps'),
      makeLog(102, 'test.test', '[VERSION] executor=v4-direct'),
    ];
    const merged = mergePhaseAndTaskLogs(phaseLogs, taskLogs);
    const contents = merged.map((l) => l.content);
    expect(contents.indexOf('Hello from taskpps')).toBe(contents.indexOf(phaseLogs[1].content) + 1);
    expect(contents.indexOf('[VERSION] executor=v4-direct')).toBe(contents.indexOf(phaseLogs[5].content) + 1);
  });

  it('没有 phase 记录的任务日志回退到末尾，且不丢行', () => {
    const taskLogs = [
      makeLog(101, 'test.hello', 'Hello from taskpps'),
      makeLog(102, 'POST.on_success.collect', 'collector output'),
    ];
    const merged = mergePhaseAndTaskLogs(phaseLogs, taskLogs);
    expect(merged.length).toBe(phaseLogs.length + taskLogs.length);
    expect(merged[merged.length - 1].content).toBe('collector output');
  });

  it('同一任务多行日志保持原始顺序', () => {
    const taskLogs = [
      makeLog(101, 'test.hello', 'line 1'),
      makeLog(102, 'test.hello', 'line 2'),
      makeLog(103, 'test.hello', 'line 3'),
    ];
    const merged = mergePhaseAndTaskLogs(phaseLogs, taskLogs);
    const contents = merged.map((l) => l.content);
    const i1 = contents.indexOf('line 1');
    expect(contents[i1 + 1]).toBe('line 2');
    expect(contents[i1 + 2]).toBe('line 3');
  });

  it('任务 phase 块存在但没有 [CMD] 行时插入到块尾', () => {
    const noCmdPhase: LogEntry[] = [
      makeLog(1, '__phase__test.hello', '[INFO] Executing task'),
      makeLog(2, '__phase__test.hello', '[INFO] Task finished'),
    ];
    const merged = mergePhaseAndTaskLogs(noCmdPhase, [makeLog(101, 'test.hello', 'output')]);
    expect(merged.map((l) => l.content)).toEqual([
      '[INFO] Executing task',
      '[INFO] Task finished',
      'output',
    ]);
  });

  it('空输入直接返回另一侧，不产生重复', () => {
    const taskLogs = [makeLog(1, 'a', 'x')];
    expect(mergePhaseAndTaskLogs([], taskLogs)).toEqual(taskLogs);
    expect(mergePhaseAndTaskLogs(phaseLogs, [])).toEqual(phaseLogs);
  });
});
