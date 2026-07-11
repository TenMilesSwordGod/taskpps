import { useState, useRef, useEffect, useCallback } from 'react';
import { Modal, Tag, Tooltip } from 'antd';
import { Terminal, Trash2, Square, Clock } from 'lucide-react';
import type { AgentWithConfig } from '@/types';
import { useExecStream, type ExecLine } from './useExecStream';

interface Props {
  open: boolean;
  agent: AgentWithConfig | null;
  onClose: () => void;
}

const DEFAULT_TIMEOUT = 60;

function lineColor(type: ExecLine['type']): string {
  switch (type) {
    case 'command': return '#7EADFF';
    case 'output': return '#C8D0E0';
    case 'error': return '#F87171';
    case 'info': return '#9CA0AC';
  }
}

function linePrefix(type: ExecLine['type']): string {
  switch (type) {
    case 'command': return '$ ';
    case 'output': return '';
    case 'error': return '';
    case 'info': return '';
  }
}

export default function ReplModal({ open, agent, onClose }: Props) {
  const { lines, status, run, cancel, clear, reset } = useExecStream();
  const [input, setInput] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [timeout, setTimeoutVal] = useState(DEFAULT_TIMEOUT);
  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    } else {
      reset();
    }
  }, [open, reset]);

  useEffect(() => {
    scrollToBottom();
  }, [lines, scrollToBottom]);

  const handleSubmit = useCallback(() => {
    const cmd = input.trim();
    if (!cmd || !agent) return;
    run(agent.agent_id, cmd, timeout);
    setHistory((prev) => [...prev, cmd]);
    setHistoryIdx(-1);
    setInput('');
  }, [input, agent, run, timeout]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (history.length === 0) return;
      const newIdx = historyIdx === -1 ? history.length - 1 : Math.max(0, historyIdx - 1);
      setHistoryIdx(newIdx);
      setInput(history[newIdx]);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (historyIdx === -1) return;
      const newIdx = historyIdx + 1;
      if (newIdx >= history.length) {
        setHistoryIdx(-1);
        setInput('');
      } else {
        setHistoryIdx(newIdx);
        setInput(history[newIdx]);
      }
    }
  }, [handleSubmit, history, historyIdx]);

  const isRunning = status === 'running';

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
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
          <span style={{ color: '#E3E4E8' }}>|</span>
          <span>命令在 agent 工作目录执行，不占用并发名额</span>
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

        {/* 终端输出区 */}
        <div
          ref={outputRef}
          style={{
            background: '#1e1e2e',
            borderRadius: 6,
            padding: '12px 14px',
            height: 360,
            overflow: 'auto',
            fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace',
            fontSize: 12.5,
            lineHeight: 1.6,
            border: '1px solid #181825',
          }}
        >
          {lines.length === 0 ? (
            <span style={{ color: '#6c7086' }}>
              输入命令并回车执行。上下箭头浏览历史命令。
            </span>
          ) : (
            lines.map((line) => (
              <div
                key={line.seq}
                style={{
                  color: lineColor(line.type),
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  minHeight: line.type === 'command' ? 'auto' : undefined,
                }}
              >
                {linePrefix(line.type)}{line.content}
              </div>
            ))
          )}
          {isRunning && (
            <span style={{ color: '#7EADFF' }}>
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
    </Modal>
  );
}