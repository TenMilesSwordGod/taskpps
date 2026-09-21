import { useState, useRef, useEffect, useCallback } from 'react';
import { Modal, Tag, Tooltip } from 'antd';
import { Terminal, Trash2, Square, Clock, Plus, X, FolderClosed, FileText } from 'lucide-react';
import type { AgentWithConfig } from '@/types';
import { execCommandStream, type ExecLine, type ExecStatus } from './execStream';
import { fetchCompletions } from './complete';

interface Props {
  open: boolean;
  agent: AgentWithConfig | null;
  onClose: () => void;
}

const DEFAULT_TIMEOUT = 60;

/** 输入提示（tip）的防抖间隔：太短会高频打接口，太长提示不跟手 */
const TIP_DEBOUNCE_MS = 150;

/** 补全候选下拉的交互状态（与后端返回的 prefix/candidates 同源） */
interface CompletionState {
  prefix: string;
  candidates: string[];
  selected: number;
  start: number;    // input 中被补全 token 的起点
  cursor: number;   // 请求时的光标位置
  // 用户是否已通过 Tab/方向键主动选择过候选。
  // 为 true 时 Enter 上屏候选；false（tip 自动弹出）时 Enter 直接执行命令，
  // 避免提示列表阻塞最高频的"输入完直接回车执行"操作
  navigated: boolean;
}

/** 给 session 自增 ID */
let sessionIdCounter = 0;

// session 数据结构
interface SessionState {
  id: string;
  name: string;
  cwd: string;           // 当前工作目录，'' 表示由后端决定（agent work dir）
  lines: ExecLine[];
  status: ExecStatus;
  history: string[];
  historyIdx: number;    // -1 表示不在浏览历史
  abortController: AbortController | null;
}

function createSession(name: string, cwd: string): SessionState {
  return {
    id: `sess-${++sessionIdCounter}`,
    name,
    cwd,
    lines: [],
    status: 'idle',
    history: [],
    historyIdx: -1,
    abortController: null,
  };
}

/** 从当前 cwd 执行 cd 命令后推断新目录 */
function resolveCwdAfterCd(currentCwd: string, command: string): string {
  const trimmed = command.trim();
  const match = trimmed.match(/^cd\s+(.+)$/);
  if (!match) return ''; // `cd` 无参数 → 回家目录，交给后端

  const raw = match[1].trim();
  // 去掉引号
  const target = raw.replace(/^["']|["']$/g, '');
  if (target.startsWith('/')) return target;           // 绝对路径
  if (target.startsWith('~')) return '';               // home
  if (target === '-') return currentCwd;               // cd - 保持当前
  // CWD 未知时无法计算相对路径，保持空（后端用 agent work dir）
  if (!currentCwd) return '';

  // 相对路径拼接
  const parts = currentCwd.split('/').filter(Boolean);
  for (const seg of target.split('/')) {
    if (seg === '..') parts.pop();
    else if (seg && seg !== '.') parts.push(seg);
  }
  return '/' + parts.join('/');
}

/** 按命令分组：每个 command 及其后续 output/error/info 构成一个 block */
interface CommandBlock {
  command: ExecLine;
  outputs: ExecLine[];   // output + error
  result: string | null; // exit_code + duration 摘要
}

function groupBlocks(lines: ExecLine[]): CommandBlock[] {
  const blocks: CommandBlock[] = [];
  let current: CommandBlock | null = null;
  for (const line of lines) {
    if (line.type === 'command') {
      current = { command: line, outputs: [], result: null };
      blocks.push(current);
    } else if (current) {
      if (line.type === 'info') {
        // 合并多条 info 为一条 result 摘要（通常会有一条 "exit_code: 0 · 123ms"）
        current.result = current.result
          ? `${current.result} · ${line.content}`
          : line.content;
      } else {
        current.outputs.push(line);
      }
    }
  }
  return blocks;
}

export default function ReplModal({ open, agent, onClose }: Props) {
  const [sessions, setSessions] = useState<SessionState[]>(() => [
    createSession(agent?.name || agent?.hostname || 'Session 1', ''),
  ]);
  const [activeId, setActiveId] = useState(sessions[0]?.id ?? '');

  // 当前 session 快捷引用
  const activeSession = sessions.find((s) => s.id === activeId) ?? sessions[0];
  const activeIdx = sessions.findIndex((s) => s.id === activeId);

  const [input, setInput] = useState('');
  const [timeout, setTimeoutVal] = useState(DEFAULT_TIMEOUT);
  // 补全候选下拉：null 表示关闭；selected 为高亮索引
  const [completion, setCompletion] = useState<CompletionState | null>(null);
  const completionAbortRef = useRef<AbortController | null>(null);
  // 请求序号：响应回来时与最新序号比对，过期结果直接丢弃（竞态保护）
  const completionSeqRef = useRef(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 用 ref 持有最新的 sessions，避免闭包过期
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;

  const scrollToBottom = useCallback(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  useEffect(() => {
    scrollToBottom();
  }, [activeSession?.lines, scrollToBottom]);

  // 用 setSessions 直接更新，避免闭包中 ref 过期
  const updateSession = useCallback((
    sessionId: string,
    updater: (s: SessionState) => SessionState,
  ) => {
    setSessions((prev) => prev.map((s) => (s.id === sessionId ? updater(s) : s)));
  }, []);

  /** 应用候选：替换 start..cursor 区间，光标移到补全结果末尾 */
  const applyCompletion = useCallback((candidate: string, start: number, cursor: number) => {
    setCompletion(null);
    setInput((prev) => {
      const next = prev.slice(0, start) + candidate + prev.slice(cursor);
      // 渲染后移动光标（React 受控输入默认把光标丢到末尾，这里显式对齐）
      requestAnimationFrame(() => {
        const el = inputRef.current;
        if (!el) return;
        el.focus();
        const pos = start + candidate.length;
        el.setSelectionRange(pos, pos);
      });
      return next;
    });
  }, []);

  /** 请求补全并处理结果。失败/超时/输入已变化 → 关闭提示，保持原输入（需求约定） */
  const requestCompletion = useCallback((line: string, cursor: number) => {
    if (!agent?.connected || !line) {
      setCompletion(null);
      return;
    }
    completionAbortRef.current?.abort();
    const controller = new AbortController();
    completionAbortRef.current = controller;
    const seq = ++completionSeqRef.current;
    const activeS = sessionsRef.current.find((s) => s.id === activeId);
    fetchCompletions(agent.agent_id, line, cursor, activeS?.cwd ?? '', controller.signal).then((result) => {
      if (seq !== completionSeqRef.current) return; // 已有更新的请求，丢弃过期结果
      const el = inputRef.current;
      if (!el || el.value !== line) return; // 用户已修改输入，丢弃
      if (!result || result.candidates.length === 0) {
        setCompletion(null);
        return;
      }
      // prefix 必须与当前输入吻合（lastIndexOf + 末尾对齐），否则输入已变
      const start = line.lastIndexOf(result.prefix, cursor);
      if (start < 0 || start + result.prefix.length !== cursor) {
        setCompletion(null);
        return;
      }
      if (result.candidates.length === 1) {
        applyCompletion(result.candidates[0], start, cursor);
      } else {
        setCompletion({ prefix: result.prefix, candidates: result.candidates, selected: 0, start, cursor, navigated: false });
      }
    });
  }, [agent, activeId, applyCompletion]);

  // 输入提示（tip）：输入变化后防抖请求补全；仅光标在末尾且有内容时触发，
  // 避免用户回改历史输入时被提示打扰。
  // 注意(2026-07): effect 必须定义在 requestCompletion 之后（const 提升问题），
  // 否则渲染期访问 requestCompletion 会抛 ReferenceError
  // v2 (2026-07): 光标位置检查必须在防抖回调内执行——输入 change 事件同步 flush
  // effect 时 selectionStart 仍是旧值（jsdom 与浏览器时序均如此），
  // 防抖窗口结束时的光标位置才是用户操作的最终状态
  useEffect(() => {
    if (!open) return;
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    const el = inputRef.current;
    if (!el || !el.value) return;
    debounceTimerRef.current = setTimeout(() => {
      const cursor = el.selectionStart ?? el.value.length;
      if (cursor !== el.value.length) return; // 用户已移动光标，不弹提示
      requestCompletion(el.value, cursor);
    }, TIP_DEBOUNCE_MS);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [input, open, requestCompletion]);

  // 切换 session
  const switchSession = useCallback((id: string) => {
    setActiveId(id);
    setInput('');
    setCompletion(null); // 会话切换后旧候选不再适用
  }, []);

  // 添加 session
  const addSession = useCallback(() => {
    setSessions((prev) => {
      const s = createSession(`Session ${prev.length + 1}`, '');
      setActiveId(s.id);
      return [...prev, s];
    });
    setInput('');
    setCompletion(null); // 新增会话并切换为活动会话，旧候选不再适用
  }, []);

  // 删除 session（至少保留一个）
  const removeSession = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessions((prev) => {
      if (prev.length <= 1) return prev;
      const target = prev.find((s) => s.id === id);
      target?.abortController?.abort();
      const next = prev.filter((s) => s.id !== id);
      if (activeId === id) {
        const idx = prev.findIndex((s) => s.id === id);
        const nextIdx = idx > 0 ? idx - 1 : 0;
        setActiveId(next[Math.min(nextIdx, next.length - 1)]?.id ?? '');
      }
      return next;
    });
    setInput('');
  }, [activeId]);

  // 执行命令
  const handleSubmit = useCallback(() => {
    const cmd = input.trim();
    if (!cmd || !agent) return;

    const activeSid = activeId;
    const controller = new AbortController();
    const isCd = /^cd(\s|$)/.test(cmd);

    // 从 ref 读取当前 session 的 cwd（保证最新）
    const session = sessionsRef.current.find((s) => s.id === activeSid);
    if (!session) return;
    const curCwd = session.cwd;

    setCompletion(null); // 执行开始后提示列表不再适用
    updateSession(activeSid, (s) => {
      s.abortController?.abort();
      return {
        ...s,
        status: 'running',
        abortController: controller,
        historyIdx: -1,
        history: [...s.history, cmd],
      };
    });
    setInput('');

    const pwdOutputs: string[] = [];
    execCommandStream(agent.agent_id, cmd, timeout, curCwd, controller.signal, {
      onAppend: (line) => {
        if (line.type === 'output' && cmd.trim() === 'pwd') {
          pwdOutputs.push(line.content.trim());
        }
        updateSession(activeSid, (s) => ({ ...s, lines: [...s.lines, line] }));
      },
      onStatus: (status) => {
        updateSession(activeSid, (s) => {
          const patch: Partial<SessionState> = { status };
          if (status === 'done') {
            if (isCd) {
              patch.cwd = resolveCwdAfterCd(s.cwd, cmd);
            } else if (cmd.trim() === 'pwd' && pwdOutputs.length === 1 && pwdOutputs[0].startsWith('/')) {
              // 从 pwd 输出提取实际路径
              patch.cwd = pwdOutputs[0];
            }
          }
          return { ...s, ...patch };
        });
      },
    });
  }, [input, agent, activeId, timeout, updateSession]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      // Esc 关闭候选列表，不影响已输入内容
      e.preventDefault();
      setCompletion(null);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (completion && completion.navigated) {
        // 用户已用 Tab/方向键选择过候选：回车 = 上屏当前高亮，不执行命令
        applyCompletion(completion.candidates[completion.selected], completion.start, completion.cursor);
        return;
      }
      handleSubmit();
    } else if (e.key === 'Tab') {
      // Tab 补全：列表已打开则循环切换高亮，否则请求补全
      e.preventDefault();
      const el = inputRef.current;
      const cursor = el?.selectionStart ?? el?.value.length ?? 0;
      if (completion && completion.candidates.length > 0) {
        setCompletion({
          ...completion,
          selected: (completion.selected + 1) % completion.candidates.length,
          navigated: true, // 用户按 Tab 即视为主动选择，之后 Enter 上屏
        });
      } else {
        requestCompletion(el?.value ?? '', cursor);
      }
    } else if ((e.key === 'ArrowUp' || e.key === 'ArrowDown') && completion) {
      // 列表打开时方向键选择候选（不翻历史）
      e.preventDefault();
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      setCompletion({
        ...completion,
        selected: (completion.selected + delta + completion.candidates.length) % completion.candidates.length,
        navigated: true, // 方向键同样视为主动选择
      });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const s = sessionsRef.current.find((x) => x.id === activeId);
      if (!s || s.history.length === 0) return;
      const newIdx = s.historyIdx === -1 ? s.history.length - 1 : Math.max(0, s.historyIdx - 1);
      updateSession(activeId, (x) => ({ ...x, historyIdx: newIdx }));
      setInput(s.history[newIdx]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const s = sessionsRef.current.find((x) => x.id === activeId);
      if (!s || s.historyIdx === -1) return;
      const newIdx = s.historyIdx + 1;
      if (newIdx >= s.history.length) {
        updateSession(activeId, (x) => ({ ...x, historyIdx: -1 }));
        setInput('');
      } else {
        updateSession(activeId, (x) => ({ ...x, historyIdx: newIdx }));
        setInput(s.history[newIdx]);
      }
    }
  }, [handleSubmit, activeId, updateSession, completion, applyCompletion, requestCompletion]);

  const cancel = useCallback(() => {
    setCompletion(null);
    const id = activeId;
    updateSession(id, (s) => {
      s.abortController?.abort();
      return { ...s, abortController: null, status: 'idle' };
    });
  }, [activeId, updateSession]);

  const clear = useCallback(() => {
    setCompletion(null);
    updateSession(activeId, (s) => ({ ...s, lines: [], status: 'idle' }));
  }, [activeId, updateSession]);

  const isRunning = activeSession?.status === 'running';

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={820}
      styles={{ body: { padding: 0 } }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Terminal size={18} color="#000000" />
          <span style={{ fontSize: 15, fontWeight: 600 }}>Web REPL</span>
          {agent && (
            <>
              <Tag color={agent.connected ? 'green' : 'default'} style={{ margin: 0 }}>
                {agent.connected ? '在线' : '离线'}
              </Tag>
              <span style={{ fontSize: 12, color: '#999999', fontFamily: 'JetBrains Mono, monospace' }}>
                {agent.name || agent.hostname || agent.agent_id}
              </span>
            </>
          )}
        </div>
      }
    >
      <div style={{ display: 'flex', height: 440, borderTop: '1px solid #E0E0E0' }}>
        {/* ===== 左侧 session 栏 ===== */}
        <div style={{
          width: 150, flexShrink: 0, background: '#FFFFFF', padding: '8px 6px',
          display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto',
          borderRight: '1px solid #E0E0E0',
        }}>
          {sessions.map((s) => (
            <div
              key={s.id}
              role="button"
              tabIndex={0}
              onClick={() => switchSession(s.id)}
              onKeyDown={(e) => { if (e.key === 'Enter') switchSession(s.id); }}
              style={{
                display: 'flex', alignItems: 'center', gap: 4, padding: '5px 8px',
                borderRadius: 4, cursor: 'pointer', fontSize: 12,
                background: s.id === activeId ? '#FFFFFF' : 'transparent',
                color: s.id === activeId ? '#000000' : '#666666',
                fontWeight: s.id === activeId ? 500 : 400,
                border: s.id === activeId ? '1px solid #CCCCCC' : '1px solid transparent',
              }}
            >
              {/* session 状态点 */}
              <span style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: s.status === 'running' ? '#000000'
                  : s.status === 'error' ? '#333333'
                  : s.status === 'done' ? '#999999'
                  : '#CCCCCC',
              }} />
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.name}
              </span>
              {sessions.length > 1 && (
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => removeSession(s.id, e)}
                  onKeyDown={(e) => { if (e.key === 'Enter') removeSession(s.id, e as any); }}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 16, height: 16, borderRadius: 3, cursor: 'pointer', flexShrink: 0,
                    color: '#999999', opacity: 0, transition: 'opacity 0.1s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.opacity = '0'; }}
                >
                  <X size={11} />
                </span>
              )}
            </div>
          ))}
          {/* + 按钮 */}
          <div
            role="button"
            tabIndex={0}
            onClick={addSession}
            onKeyDown={(e) => { if (e.key === 'Enter') addSession(); }}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
              padding: '5px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 12,
              color: '#666666', marginTop: 4, border: '1px dashed #CCCCCC',
            }}
          >
            <Plus size={12} />
            <span>添加 Session</span>
          </div>
        </div>

        {/* ===== 右侧终端区 ===== */}
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '10px 12px' }}>
          {/* 提示条 */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, fontSize: 11, color: '#999999',
          }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
              <Clock size={11} />
              超时
            </span>
            <input
              type="number"
              min={5}
              max={600}
              value={timeout}
              onChange={(e) => setTimeoutVal(Math.max(5, Math.min(600, Number(e.target.value) || DEFAULT_TIMEOUT)))}
              style={{
                width: 50, fontSize: 11, padding: '1px 4px', borderRadius: 3,
                border: '1px solid #CCCCCC', textAlign: 'center',
                fontFamily: 'JetBrains Mono, monospace', color: '#333333',
              }}
            />
            <span>秒</span>
            {activeSession?.cwd && (
              <>
                <span style={{ color: '#E0E0E0' }}>|</span>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#999999' }}>
                  {activeSession.cwd}
                </span>
              </>
            )}
            <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
              <Tooltip title={isRunning ? '取消执行' : '清屏'}>
                <span
                  role="button"
                  tabIndex={0}
                  onClick={() => { if (isRunning) cancel(); else clear(); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') { if (isRunning) cancel(); else clear(); } }}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 24, height: 24, borderRadius: 4, cursor: 'pointer',
                    color: isRunning ? '#FFFFFF' : '#999999', transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#F0F0F0'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = ''; }}
                >
                  {isRunning ? <Square size={13} /> : <Trash2 size={13} />}
                </span>
              </Tooltip>
            </div>
          </div>

          {/* 终端输出区 — VS Code 风格，按命令分组 */}
          <div
            ref={outputRef}
            style={{
              background: '#000000',
              borderRadius: 6,
              padding: '12px 14px',
              flex: 1,
              overflow: 'auto',
              fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace',
              fontSize: 12.5,
              lineHeight: 1.6,
              border: '1px solid #333333',
            }}
          >
            {(!activeSession || activeSession.lines.length === 0) ? (
              <span style={{ color: '#999999' }}>
                输入命令并回车执行。上下箭头浏览历史命令。
              </span>
            ) : (() => {
              const blocks = groupBlocks(activeSession.lines);
              const lastBlock = blocks.at(-1);
              return blocks.map((block, bi) => (
                <div key={bi} style={{ marginBottom: block === lastBlock && isRunning ? 0 : 8 }}>
                  {/* 命令行 + 结果信息同行 */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                    <span style={{ color: '#FFFFFF', fontWeight: 600, flexShrink: 0, userSelect: 'none' }}>$</span>
                    <span style={{ color: '#FFFFFF', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {block.command.content}
                    </span>
                    {block.result && (
                      <span style={{
                        fontSize: 11, color: '#888888', flexShrink: 0,
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                      }}>
                        {/exit_code:\s*0/.test(block.result) ? (
                          <span style={{ color: '#FFFFFF' }}>✔</span>
                        ) : /exit_code:\s*[1-9]/.test(block.result) ? (
                          <span style={{ color: '#FFFFFF' }}>✘</span>
                        ) : null}
                        <span>{block.result}</span>
                      </span>
                    )}
                  </div>
                  {/* 输出行 */}
                  {block.outputs.map((line) => (
                    <div
                      key={line.seq}
                      style={{
                        color: line.type === 'error' ? '#FFFFFF' : '#D4D4D4',
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        paddingLeft: 20,
                      }}
                    >
                      {line.content}
                    </div>
                  ))}
                </div>
              ))
            })()}
            {isRunning && (
              <span style={{ color: '#FFFFFF', marginLeft: 4 }}>
                <span className="animate-pulse">▎</span>
              </span>
            )}
          </div>

          {/* 补全候选下拉（输入框上方弹出，仅多候选时显示） */}
          {completion && completion.candidates.length > 0 && (
            <div
              role="listbox"
              data-testid="completion-list"
              style={{
                position: 'relative',
                marginTop: 8,
                marginBottom: -52,
                zIndex: 10,
              }}
            >
              <div style={{
                background: '#000000',
                border: '1px solid #333333',
                borderRadius: 6,
                padding: '4px',
                maxHeight: 180,
                overflowY: 'auto',
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
              }}>
                {completion.candidates.map((c, idx) => {
                  const isDir = c.endsWith('/');
                  const isFile = c.includes('/');
                  const Icon = isDir ? FolderClosed : isFile ? FileText : Terminal;
                  return (
                    <div
                      key={c + idx}
                      role="option"
                      aria-selected={idx === completion.selected}
                      onMouseEnter={() => setCompletion({ ...completion, selected: idx })}
                      onClick={() => applyCompletion(c, completion.start, completion.cursor)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '4px 8px', borderRadius: 4, cursor: 'pointer',
                        fontSize: 12.5, fontFamily: 'JetBrains Mono, monospace',
                        color: '#D4D4D4',
                        background: idx === completion.selected ? '#2A2A2A' : 'transparent',
                      }}
                    >
                      <Icon size={13} color={isDir ? '#999999' : isFile ? '#999999' : '#999999'} />
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {c}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {/* 命令输入行 */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            marginTop: 8, padding: '8px 12px',
            background: '#000000', borderRadius: 6,
            border: '1px solid #333333',
          }}>
            <span style={{
              color: agent?.connected ? '#FFFFFF' : '#999999',
              fontFamily: 'JetBrains Mono, monospace', fontSize: 13,
              flexShrink: 0, fontWeight: 500,
            }}>
              $
            </span>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!agent?.connected}
              placeholder={agent?.connected ? '输入命令…' : 'Agent 离线，无法执行'}
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                color: '#E5E5E5', fontFamily: 'JetBrains Mono, monospace',
                fontSize: 13, caretColor: '#FFFFFF',
              }}
            />
            {isRunning && (
              <span style={{
                fontSize: 10, color: '#FFFFFF', flexShrink: 0,
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}>
                <span className="animate-pulse">●</span> 执行中
              </span>
            )}
          </div>
        </div>
      </div>
    </Modal>
  );
}
