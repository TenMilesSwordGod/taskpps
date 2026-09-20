/**
 * v2 (2026-09): console.log 解析与 phase/任务日志合并工具。
 *
 * 后端 PipelineRunner 以 [PIPELINE/SUB/TASK:*:SETUP|TEARDOWN] 标签标记作用域，
 * 前端按「最近一个标签」给无标签行归属作用域。后端会在任务结束、
 * 下一层级/汇总日志之前补发 SUB 标签，这里只负责解析，不做二次猜测。
 *
 * 抽出独立模块的原因：RunDetailPage（扁平日志视图）和 TaskTree（phase 分组树）
 * 原先把同一套正则各自实现一遍，修复归属问题时两处容易不一致。
 */
import type { LogEntry } from './hooks/useSSELogs';

export type ConsoleScope = 'pipeline' | 'sub' | 'task';
export type ConsolePhase = 'setup' | 'teardown';

export interface ConsoleTag {
  scope: ConsoleScope;
  name: string;
  phase: ConsolePhase;
}

export type ConsoleToken =
  | { kind: 'tag'; tag: ConsoleTag }
  | { kind: 'line'; tag: ConsoleTag; content: string; timestamp: number };

export interface PhaseLogEntry {
  /** phase 名：pipeline / 子流水线名 / 限定任务名 */
  phase: string;
  content: string;
  timestamp: number;
}

const TAG_PATTERN = /^\[(PIPELINE:(SETUP|TEARDOWN)|SUB:([^:]+):(SETUP|TEARDOWN)|TASK:([^:]+):(SETUP|TEARDOWN))\]/;

/** console.log 行内嵌的服务端 ISO 时间戳（标签行与 _write_pipeline_log 行都有） */
const TIMESTAMP_PATTERN = /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))/;

const DEFAULT_TAG: ConsoleTag = { scope: 'pipeline', name: 'pipeline', phase: 'setup' };

function parseTag(line: string): ConsoleTag | null {
  const match = line.match(TAG_PATTERN);
  if (!match) return null;
  if (match[1].startsWith('PIPELINE:')) {
    return { scope: 'pipeline', name: 'pipeline', phase: match[2].toLowerCase() as ConsolePhase };
  }
  if (match[1].startsWith('SUB:')) {
    return { scope: 'sub', name: match[3], phase: match[4].toLowerCase() as ConsolePhase };
  }
  return { scope: 'task', name: match[5], phase: match[6].toLowerCase() as ConsolePhase };
}

/**
 * 把 console.log 文本切成有序 token：标签 token 用于树分组，
 * 行 token 携带当前生效的作用域标签与继承的时间戳。
 */
export function tokenizeConsoleLog(content: string): ConsoleToken[] {
  const tokens: ConsoleToken[] = [];
  let current = DEFAULT_TAG;
  let lastTimestamp = 0;

  for (const line of content.split('\n')) {
    const tsMatch = line.match(TIMESTAMP_PATTERN);
    if (tsMatch) {
      const parsed = Date.parse(tsMatch[1]);
      if (!Number.isNaN(parsed)) lastTimestamp = parsed;
    }

    const tag = parseTag(line);
    if (tag) {
      current = tag;
      tokens.push({ kind: 'tag', tag });
      continue;
    }
    tokens.push({ kind: 'line', tag: current, content: line, timestamp: lastTimestamp });
  }

  return tokens;
}

/** 扁平日志视图用：把非空行转成带 phase 和时间戳的条目（标签行本身不展示） */
export function parsePhaseLogEntries(content: string): PhaseLogEntry[] {
  const entries: PhaseLogEntry[] = [];
  for (const token of tokenizeConsoleLog(content)) {
    if (token.kind === 'line' && token.content.trim()) {
      entries.push({ phase: token.tag.name, content: token.content, timestamp: token.timestamp });
    }
  }
  return entries;
}

/**
 * 把任务日志（SSE，来自每个 task 的 log 文件）按时间顺序插回 phase 日志中，
 * 避免 Debug 视图把任务输出整体追加到流水线结束之后。
 *
 * 插入点选择任务 phase 块内最后一条 [CMD] 行之后：任务真正输出发生在命令下发之后、
 * result 记录之前，这样 stdout 会出现在结果行之前而不是任务结束之后。
 * 找不到 phase 块的任务（tail 截断、POST 任务、实时运行尚未刷新 console）回退到末尾。
 */
export function mergePhaseAndTaskLogs(phaseLogs: LogEntry[], taskLogs: LogEntry[]): LogEntry[] {
  if (phaseLogs.length === 0 || taskLogs.length === 0) {
    return [...phaseLogs, ...taskLogs];
  }

  const PHASE_PREFIX = '__phase__';
  const blockEnd = new Map<string, number>();
  const lastCmd = new Map<string, number>();
  phaseLogs.forEach((entry, index) => {
    if (!entry.taskName.startsWith(PHASE_PREFIX)) return;
    const phase = entry.taskName.slice(PHASE_PREFIX.length);
    if (!phase) return;
    blockEnd.set(phase, index);
    if (entry.content.includes('[CMD]')) lastCmd.set(phase, index);
  });

  const insertions = new Map<number, LogEntry[]>();
  const unmatched: LogEntry[] = [];
  for (const entry of taskLogs) {
    const at = lastCmd.get(entry.taskName) ?? blockEnd.get(entry.taskName);
    if (at === undefined) {
      unmatched.push(entry);
      continue;
    }
    const bucket = insertions.get(at);
    if (bucket) bucket.push(entry);
    else insertions.set(at, [entry]);
  }

  const merged: LogEntry[] = [];
  phaseLogs.forEach((entry, index) => {
    merged.push(entry);
    const bucket = insertions.get(index);
    if (bucket) merged.push(...bucket);
  });
  merged.push(...unmatched);
  return merged;
}
