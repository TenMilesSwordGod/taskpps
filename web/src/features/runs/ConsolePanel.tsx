import { useState } from 'react';
import { Button, Tag, Tooltip, Empty, Select, Space } from 'antd';
import { ChevronDown, ChevronRight, FileText, RefreshCw, Download, AlertCircle, Bug, Info, Terminal, AlertTriangle } from 'lucide-react';
import { useRunConsole } from '@/api/runs';

interface ConsolePanelProps {
  runId: string;
}

/** 解析 console 中的 exit code 和关键错误行 */
function parseConsoleSummary(content: string) {
  const lines = content.split('\n');
  const exitCodes: { taskName: string; code: number }[] = [];
  const errors: string[] = [];

  for (const line of lines) {
    // 匹配 "[task_name] exit_code: N"
    const ecMatch = line.match(/\[([^\]]+)\]\s*(?:.*?exit[:-]?\s*code[:=]?\s*|exit_code[:=]?\s*)(-?\d+)/i);
    if (ecMatch) {
      exitCodes.push({ taskName: ecMatch[1], code: parseInt(ecMatch[2], 10) });
    }
    // 匹配 ERROR/WARN 级别行
    if (/\[ERROR\]|\[FATAL\]|Traceback/i.test(line)) {
      errors.push(line.trim());
    }
  }

  return { exitCodes, errorCount: errors.length };
}

type LogLevel = 'error' | 'warn' | 'info' | 'debug' | 'unknown';

const LEVEL_STYLE: Record<LogLevel, { color: string; icon: typeof Bug }> = {
  error: { color: '#fca5a5', icon: AlertCircle },
  warn: { color: '#fcd34d', icon: AlertTriangle },
  info: { color: '#93c5fd', icon: Info },
  debug: { color: '#9ca3af', icon: Bug },
  unknown: { color: '#d1d5db', icon: Terminal },
};

function detectLevel(line: string): LogLevel {
  if (/\[ERROR\]|\[FATAL\]|Traceback|Error:/i.test(line)) return 'error';
  if (/\[WARN\]/i.test(line)) return 'warn';
  if (/\[DEBUG\]/i.test(line)) return 'debug';
  if (/\[INFO\]/i.test(line)) return 'info';
  return 'unknown';
}

/** 嵌入式 Pipeline Console Log 面板（可折叠） */
export default function ConsolePanel({ runId }: ConsolePanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [tail, setTail] = useState<number | undefined>(500);
  const { data, isLoading, refetch } = useRunConsole(runId, tail);

  const summary = data?.content ? parseConsoleSummary(data.content) : { exitCodes: [], errorCount: 0 };

  return (
    <div style={{ borderTop: '1px solid #e5e7eb', background: '#fafafa' }}>
      {/* 标题栏 — 可点击折叠 */}
      <div
        onClick={() => setCollapsed(!collapsed)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '6px 12px',
          cursor: 'pointer',
          background: '#f3f4f6',
          borderBottom: collapsed ? 'none' : '1px solid #e5e7eb',
          userSelect: 'none',
        }}
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
        <FileText size={14} color="#6b7280" />
        <span style={{ fontSize: 13, fontWeight: 500, color: '#374151' }}>System Console Log</span>

        {data && (
          <>
            <Tag style={{ margin: 0, padding: '0 6px', fontSize: 11, lineHeight: '18px', height: 20 }}>
              {data.exists ? `${data.lines} 行` : '无文件'}
            </Tag>
            {summary.errorCount > 0 && (
              <Tag color="error" style={{ margin: 0, padding: '0 6px', fontSize: 11, lineHeight: '18px', height: 20 }}>
                <AlertCircle size={10} style={{ marginRight: 2 }} />
                {summary.errorCount} 错误
              </Tag>
            )}
          </>
        )}

        {/* Exit codes 摘要 */}
        {summary.exitCodes.length > 0 && (
          <div style={{ display: 'flex', gap: 4, marginLeft: 8, flexWrap: 'wrap' }}>
            {summary.exitCodes.map((ec) => (
              <Tooltip key={ec.taskName} title={`${ec.taskName} → Exit ${ec.code}`}>
                <Tag
                  color={ec.code === 0 ? 'success' : 'error'}
                  style={{ margin: 0, padding: '0 6px', fontSize: 11, lineHeight: '18px', height: 20, cursor: 'default' }}
                >
                  {ec.taskName.split('.').pop()} : {ec.code}
                </Tag>
              </Tooltip>
            ))}
          </div>
        )}

        <div style={{ flex: 1 }} />

        {/* 工具栏（折叠时隐藏） */}
        {!collapsed && (
          <Space size={4} onClick={(e) => e.stopPropagation()}>
            <Select
              size="small"
              value={tail}
              onChange={setTail}
              style={{ width: 90 }}
              options={[
                { label: '200 行', value: 200 },
                { label: '500 行', value: 500 },
                { label: '全文', value: undefined },
              ]}
            />
            <Button size="small" icon={<RefreshCw size={12} />} loading={isLoading} onClick={() => refetch()}>
              刷新
            </Button>
            <Button
              size="small"
              icon={<Download size={12} />}
              disabled={!data?.content}
              onClick={() => {
                const blob = new Blob([data?.content ?? ''], { type: 'text/plain;charset=utf-8' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `console-${runId}.log`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
              }}
            />
          </Space>
        )}
      </div>

      {/* 日志内容 */}
      {!collapsed && (
        <div
          style={{
            background: '#0d1117',
            fontFamily: '"JetBrains Mono", "Fira Code", monospace',
            fontSize: 12,
            lineHeight: '20px',
            maxHeight: 280,
            overflow: 'auto',
            padding: data?.content ? '4px 0' : 0,
          }}
        >
          {isLoading ? (
            <div style={{ color: '#8b949e', textAlign: 'center', padding: 40 }}>加载中…</div>
          ) : !data?.exists ? (
            <div style={{ color: '#8b949e', textAlign: 'center', padding: 40 }}>
              console.log 文件不存在（pipeline 可能尚未启动或日志路径未就绪）
            </div>
          ) : !data?.content ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={<span style={{ color: '#8b949e' }}>暂无日志</span>} />
          ) : (
            data.content.split('\n').map((line, i) => {
              const level = detectLevel(line);
              const ls = LEVEL_STYLE[level];
              return (
                <div
                  key={i}
                  style={{
                    padding: '1px 12px',
                    borderLeft: level === 'error' ? '3px solid #f85149' : '3px solid transparent',
                    background: level === 'error' ? 'rgba(248,81,73,0.08)' : 'transparent',
                    whiteSpace: 'pre',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  <span style={{ color: ls.color, marginRight: 8, fontWeight: 500, fontSize: 11 }}>
                    {level.toUpperCase().padEnd(5)}
                  </span>
                  <span style={{ color: '#c9d1d9' }}>{line}</span>
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
