import { useState, useRef, useEffect, useCallback } from 'react';
import { Modal, Tag, Tooltip } from 'antd';
import { Terminal, Trash2, Square, Clock, Plus, X } from 'lucide-react';
import type { AgentWithConfig } from '@/types';
import { execCommandStream, type ExecLine, type ExecStatus } from './execStream';

interface Props {
  open: boolean;
  agent: AgentWithConfig | null;
  onClose: () => void;
}

const DEFAULT_TIMEOUT = 60;

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

  // 切换 session
  const switchSession = useCallback((id: string) => {
    setActiveId(id);
    setInput('');
  }, []);

  // 添加 session
  const addSession = useCallback(() => {
    setSessions((prev) => {
      const s = createSession(`Session ${prev.length + 1}`, '');
      setActiveId(s.id);
      return [...prev, s];
    });
    setInput('');
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
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
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
  }, [handleSubmit, activeId, updateSession]);

  const cancel = useCallback(() => {
    const id = activeId;
    updateSession(id, (s) => {
      s.abortController?.abort();
      return { ...s, abortController: null, status: 'idle' };
    });
  }, [activeId, updateSession]);

  const clear = useCallback(() => {
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
          <Terminal size={18} color="#3D5BFF" />
          <span style={{ fontSize: 15, fontWeight: 600 }}>Web REPL</span>
          {agent && (
            <>
              <Tag color={agent.connected ? 'green' : 'default'} style={{ margin: 0 }}>
                {agent.connected ? '在线' : '离线'}
              </Tag>
              <span style={{ fontSize: 12, color: '#7C7F88', fontFamily: 'JetBrains Mono, monospace' }}>
                {agent.name || agent.hostname || agent.agent_id}
              </span>
            </>
          )}
        </div>
      }
    >
      <div style={{ display: 'flex', height: 440, borderTop: '1px solid #E3E4E8' }}>
        {/* ===== 左侧 session 栏 ===== */}
        <div style={{
          width: 150, flexShrink: 0, background: '#F2F3F5', padding: '8px 6px',
          display: 'flex', flexDirection: 'column', gap: 2, overflowY: 'auto',
          borderRight: '1px solid #E3E4E8',
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
                color: s.id === activeId ? '#121620' : '#6C7086',
                fontWeight: s.id === activeId ? 500 : 400,
                border: s.id === activeId ? '1px solid #D0D5DD' : '1px solid transparent',
              }}
            >
              {/* session 状态点 */}
              <span style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: s.status === 'running' ? '#f59e0b'
                  : s.status === 'error' ? '#ef4444'
                  : s.status === 'done' ? '#10b981'
                  : '#9CA0AC',
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
                    color: '#9CA0AC', opacity: 0, transition: 'opacity 0.1s',
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
              color: '#6C7086', marginTop: 4, border: '1px dashed #D0D5DD',
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
            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, fontSize: 11, color: '#7C7F88',
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
                border: '1px solid #E3E4E8', textAlign: 'center',
                fontFamily: 'JetBrains Mono, monospace', color: '#121620',
              }}
            />
            <span>秒</span>
            {activeSession?.cwd && (
              <>
                <span style={{ color: '#E3E4E8' }}>|</span>
                <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#9CA0AC' }}>
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
                    color: isRunning ? '#ef4444' : '#7C7F88', transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#F6F6F8'; }}
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
              background: '#1e1e2e',
              borderRadius: 6,
              padding: '12px 14px',
              flex: 1,
              overflow: 'auto',
              fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace',
              fontSize: 12.5,
              lineHeight: 1.6,
              border: '1px solid #181825',
            }}
          >
            {(!activeSession || activeSession.lines.length === 0) ? (
              <span style={{ color: '#6c7086' }}>
                输入命令并回车执行。上下箭头浏览历史命令。
              </span>
            ) : (() => {
              const blocks = groupBlocks(activeSession.lines);
              const lastBlock = blocks.at(-1);
              return blocks.map((block, bi) => (
                <div key={bi} style={{ marginBottom: block === lastBlock && isRunning ? 0 : 8 }}>
                  {/* 命令行 + 结果信息同行 */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                    <span style={{ color: '#10b981', fontWeight: 600, flexShrink: 0, userSelect: 'none' }}>$</span>
                    <span style={{ color: '#7EADFF', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                      {block.command.content}
                    </span>
                    {block.result && (
                      <span style={{
                        fontSize: 11, color: '#6c7086', flexShrink: 0,
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                      }}>
                        {/exit_code:\s*0/.test(block.result) ? (
                          <span style={{ color: '#10b981' }}>✔</span>
                        ) : /exit_code:\s*[1-9]/.test(block.result) ? (
                          <span style={{ color: '#F87171' }}>✘</span>
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
                        color: line.type === 'error' ? '#F87171' : '#C8D0E0',
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
              <span style={{ color: '#7EADFF', marginLeft: 4 }}>
                <span className="animate-pulse">▎</span>
              </span>
            )}
          </div>

          {/* 命令输入行 */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            marginTop: 8, padding: '8px 12px',
            background: '#1e1e2e', borderRadius: 6,
            border: '1px solid #181825',
          }}>
            <span style={{
              color: agent?.connected ? '#10b981' : '#6c7086',
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
                color: '#C8D0E0', fontFamily: 'JetBrains Mono, monospace',
                fontSize: 13, caretColor: '#C8D0E0',
              }}
            />
            {isRunning && (
              <span style={{
                fontSize: 10, color: '#f59e0b', flexShrink: 0,
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
