import { memo, useState, useCallback } from 'react';
import { Tooltip, Popconfirm, Tag, Popover } from 'antd';
import type { AgentWithConfig, PendingCommandItem } from '@/types';
import {
  Cpu, Globe, Hash, Activity, Wifi, WifiOff, Plug, Unplug, HelpCircle,
  CloudUpload, Loader2, Info, FolderOpen, ExternalLink, Clock, Timer,
} from 'lucide-react';
import { useDeployAgent, usePendingCommands } from '@/api/agents';
import { useNavigate } from 'react-router-dom';

interface ServerCardProps {
  agent: AgentWithConfig;
  detectedSystem?: string;
  detectedArch?: string;
  onShowDetail?: (agent: AgentWithConfig) => void;
}

function getOsIcon(system: string): string {
  const s = (system || '').toLowerCase();
  if (s.includes('linux')) return '/static/servers/linux.svg';
  if (s.includes('darwin') || s.includes('macos') || s.includes('mac os') || s.includes('apple')) return '/static/servers/apple.svg';
  if (s.includes('windows')) return '/static/servers/windows.svg';
  return '/static/servers/server.svg';
}

function getSystemLabel(system: string): string {
  const s = (system || '').toLowerCase();
  if (!s) return 'Unknown';
  if (s.includes('debian')) return 'Debian';
  if (s.includes('ubuntu')) return 'Ubuntu';
  if (s.includes('centos')) return 'CentOS';
  if (s.includes('redhat') || s.includes('rhel')) return 'Red Hat';
  if (s.includes('alpine')) return 'Alpine';
  if (s.includes('arch')) return 'Arch';
  if (s.includes('darwin') || s.includes('macos') || s.includes('mac os')) return 'macOS';
  if (s.includes('windows')) return 'Windows';
  if (s.includes('linux')) return 'Linux';
  return system.charAt(0).toUpperCase() + system.slice(1);
}

function getArchLabel(arch: string): string {
  const a = (arch || '').toLowerCase();
  if (!a) return 'Unknown';
  if (a.includes('x86_64') || a.includes('amd64')) return 'x86_64';
  if (a.includes('aarch64') || a.includes('arm64')) return 'ARM64';
  if (a.includes('i386') || a.includes('i686') || a === 'x86') return 'x86';
  if (a.includes('armv7') || a.includes('armv6')) return 'ARM';
  return arch;
}

function getTypeLabel(type: string): string {
  if (!type) return 'Local';
  if (type.startsWith('ssh-')) return 'SSH';
  if (type === 'local') return 'Local';
  if (type === 'execution-agent' || type === 'agent' || type === 'websocket') return 'Agent';
  return type;
}

function fallbackSystem(type: string): string {
  if (!type) return 'Local';
  if (type.startsWith('ssh-')) return 'Linux';
  if (type === 'local') return 'Local';
  return '';
}

function fallbackArch(): string {
  return '';
}

function NetStatusIcon({ netStatus }: { netStatus: 'unknown' | 'reachable' | 'unreachable' }) {
  if (netStatus === 'reachable') {
    return (
      <Tooltip title="网络可达">
        <Plug size={14} color="#10b981" />
      </Tooltip>
    );
  }
  if (netStatus === 'unreachable') {
    return (
      <Tooltip title="网络不可达">
        <Unplug size={14} color="#ef4444" />
      </Tooltip>
    );
  }
  return (
    <Tooltip title="网络状态未知">
      <HelpCircle size={14} color="#7C7F88" />
    </Tooltip>
  );
}

function formatTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString('zh-CN');
}

function formatDateTime(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function formatRelativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Math.floor((Date.now() / 1000) - ts);
  if (diff < 0) return '刚刚';
  if (diff < 60) return `${diff}秒前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

function osArchLabel(systemLabel: string, archLabel: string): string {
  const parts: string[] = [];
  if (systemLabel && systemLabel !== '—') parts.push(systemLabel);
  if (archLabel && archLabel !== '—') parts.push(archLabel);
  return parts.length > 0 ? parts.join(' · ') : '—';
}

function formatDuration(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m ${sec}s`;
}

function CommandRow({
  cmd,
  index,
  status,
  onRunClick,
}: {
  cmd: PendingCommandItem;
  index: number;
  status: 'running' | 'queued';
  onRunClick: (runId: string) => void;
}) {
  const isRunning = status === 'running';
  return (
    <div
      key={cmd.command_id}
      style={{ padding: '6px 12px', borderBottom: '1px solid #E3E4E8', fontSize: 12 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              width: 18,
              height: 18,
              borderRadius: 4,
              background: isRunning ? 'rgba(126, 173, 255, 0.1)' : '#E3E4E8',
              color: isRunning ? '#3D5BFF' : '#7C7F88',
              fontSize: 10,
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="执行顺序"
          >
            {index + 1}
          </span>
          <span style={{ fontWeight: 600, color: '#121620' }}>
            {cmd.task_name || <span style={{ color: '#7C7F88' }}>未知任务</span>}
          </span>
        </span>
        <span
          style={{
            color: isRunning ? '#3D5BFF' : '#7C7F88',
            fontSize: 11,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 2,
          }}
        >
          {isRunning ? <Loader2 size={10} className="animate-spin" /> : <Clock size={10} />}
          {formatDuration(cmd.duration_s)}
        </span>
      </div>
      <div
        style={{
          fontFamily: 'monospace',
          fontSize: 11,
          color: '#121620',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
        title={cmd.command}
      >
        {cmd.command || '—'}
      </div>
      {cmd.run_id && (
        <div style={{ marginTop: 3 }}>
          <span
            role="button"
            tabIndex={0}
            onClick={() => onRunClick(cmd.run_id)}
            onKeyDown={(e) => { if (e.key === 'Enter') onRunClick(cmd.run_id); }}
            style={{ fontSize: 11, color: '#3D5BFF', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 3 }}
          >
            <ExternalLink size={10} />
            {cmd.run_id.slice(0, 8)}
          </span>
        </div>
      )}
    </div>
  );
}

function PendingCommandsContent({ commands, onRunClick }: { commands?: PendingCommandItem[]; onRunClick: (runId: string) => void }) {
  if (!commands?.length) {
    return <div style={{ padding: '8px 12px', color: '#7C7F88', fontSize: 12 }}>暂无运行中或等待中命令</div>;
  }
  const running = commands.filter((c) => c.status === 'running');
  const queued = commands.filter((c) => c.status === 'queued');
  return (
    <div>
      {running.length > 0 && (
        <div style={{ padding: '4px 12px', fontSize: 11, color: '#3D5BFF', fontWeight: 600, background: '#F6F6F8' }}>
          运行中 ({running.length})
        </div>
      )}
      {running.map((cmd, index) => (
        <CommandRow key={cmd.command_id} cmd={cmd} index={index} status="running" onRunClick={onRunClick} />
      ))}
      {queued.length > 0 && (
        <div style={{ padding: '4px 12px', fontSize: 11, color: '#7C7F88', fontWeight: 600, background: '#F6F6F8' }}>
          等待中 ({queued.length})
        </div>
      )}
      {queued.map((cmd, index) => (
        <CommandRow key={cmd.command_id} cmd={cmd} index={index} status="queued" onRunClick={onRunClick} />
      ))}
    </div>
  );
}

function LastExecTime({ timestamp }: { timestamp: number }) {
  const [showRelative, setShowRelative] = useState(false);
  const [flipping, setFlipping] = useState(false);

  const handleToggle = useCallback(() => {
    setFlipping(true);
    setTimeout(() => {
      setShowRelative((v) => !v);
      setFlipping(false);
    }, 150);
  }, []);

  if (!timestamp) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#7C7F88', marginBottom: 6 }}>
        <Timer size={12} style={{ flexShrink: 0 }} />
        <span>暂无执行记录</span>
      </div>
    );
  }

  const displayText = showRelative ? formatRelativeTime(timestamp) : formatDateTime(timestamp);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleToggle}
      onKeyDown={(e) => { if (e.key === 'Enter') handleToggle(); }}
      title="点击切换相对/绝对时间"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 5,
        fontSize: 11,
        color: '#121620',
        cursor: 'pointer',
        marginBottom: 6,
        userSelect: 'none',
      }}
    >
      <Timer size={12} style={{ flexShrink: 0, color: '#7C7F88' }} />
      <span
        style={{
          display: 'inline-block',
          transform: flipping ? 'rotateX(90deg)' : 'rotateX(0deg)',
          opacity: flipping ? 0 : 1,
          transition: 'transform 0.15s ease-in-out, opacity 0.15s ease-in-out',
          transformOrigin: 'center center',
        }}
      >
        {displayText}
      </span>
    </div>
  );
}

function ServerCard({ agent, detectedSystem, detectedArch, onShowDetail }: ServerCardProps) {
  const online = agent.connected;
  const deploy = useDeployAgent();
  const navigate = useNavigate();
  const isDeploying = deploy.isPending && deploy.variables === agent.agent_id;
  const [popoverOpen, setPopoverOpen] = useState(false);
  const hasQueue = agent.running_commands > 0 || agent.queued_commands > 0;
  const { data: pendingCommands } = usePendingCommands(agent.agent_id, popoverOpen && hasQueue);

  const effectiveSystem = detectedSystem || agent.system || fallbackSystem(agent.type);
  const effectiveArch = detectedArch || agent.arch || fallbackArch();
  const osIcon = getOsIcon(effectiveSystem);
  const systemLabel = effectiveSystem ? getSystemLabel(effectiveSystem) : '—';
  const archLabel = effectiveArch ? getArchLabel(effectiveArch) : '—';
  const typeLabel = getTypeLabel(agent.type);

  const displayName = agent.name || agent.hostname || agent.agent_id;
  const displayIp = agent.ip || (agent.host ? (agent.port ? `${agent.host}:${agent.port}` : agent.host) : '—');
  const versionDisplay = agent.agent_version ? `v${agent.agent_version}` : '—';
  const osArchText = osArchLabel(systemLabel, archLabel);
  const maxParallel = agent.max_parallel ?? 1;

  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E3E4E8',
        borderLeft: online ? '3px solid #10b981' : '3px solid #E3E4E8',
        borderRadius: '3px 8px 8px 3px',
        padding: '12px 14px',
        transition: 'box-shadow 0.22s cubic-bezier(0.76, 0, 0.24, 1), transform 0.22s cubic-bezier(0.76, 0, 0.24, 1), border-color 0.22s cubic-bezier(0.76, 0, 0.24, 1)',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = 'rgba(17, 26, 74, 0.1) 0px 1px 3px 0px';
        e.currentTarget.style.transform = 'translateY(-1px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      {/* 顶部：图标 + 名称 + 状态 + 连接 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 8,
            background: '#F6F6F8',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            opacity: online ? 1 : 0.6,
          }}
        >
          <img src={osIcon} alt="" style={{ width: 22, height: 22, objectFit: 'contain' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: '#121620',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={displayName}
            >
              {displayName}
            </span>
            <Tag
              color={online ? 'green' : 'default'}
              style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 5px', borderRadius: 3, border: 'none' }}
            >
              {online ? '在线' : '离线'}
            </Tag>
          </div>
          <div style={{ fontSize: 11, color: '#7C7F88', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
            <span title={agent.source_file || agent.agent_id}>{agent.agent_id}</span>
            <span style={{ color: '#E3E4E8' }}>·</span>
            <span>{typeLabel}</span>
            {agent.project_id && (
              <>
<span style={{ color: '#E3E4E8' }}>·</span>
                <Tooltip title={`项目: ${agent.project_name || agent.project_id}`}>
                  <Tag
                    icon={<FolderOpen size={10} />}
                    style={{ margin: 0, fontSize: 10, lineHeight: '16px', paddingInline: 4, borderRadius: 4 }}
                    color="blue"
                  >
                    {agent.project_id}
                  </Tag>
                </Tooltip>
              </>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, paddingTop: 2 }}>
          <Tooltip title={online ? 'Agent 已连接' : 'Agent 未连接'}>
            {online ? <Wifi size={14} color="#10b981" /> : <WifiOff size={14} color="#7C7F88" />}
          </Tooltip>
          <NetStatusIcon netStatus={agent.net_status} />
        </div>
      </div>

      {/* 信息行：简洁双行布局 */}
      <div
        style={{
          background: '#F6F6F8',
          borderRadius: 6,
          padding: '8px 10px',
          marginBottom: 8,
        }}
      >
        <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#121620', minWidth: 0 }}>
            <Globe size={11} style={{ flexShrink: 0, color: '#7C7F88' }} />
            <span style={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {displayIp}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#121620', flexShrink: 0 }}>
            <Hash size={11} style={{ flexShrink: 0, color: '#7C7F88' }} />
            <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{versionDisplay}</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 5, fontSize: 12, color: '#121620' }}>
          <Cpu size={11} style={{ flexShrink: 0, color: '#7C7F88' }} />
          <span style={{ fontSize: 12 }}>{osArchText}</span>
        </div>
      </div>

      {/* 上次执行时间 */}
      <LastExecTime timestamp={agent.last_execution_time} />

      {/* 底部：运行命令数 / 最大并发 / 连接时间 + 操作按钮 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: '#7C7F88' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Popover
            open={popoverOpen}
            onOpenChange={(open) => setPopoverOpen(open && hasQueue)}
            trigger="click"
            placement="topLeft"
            title={
              <div style={{ padding: '6px 12px', fontSize: 12, fontWeight: 600, color: '#121620', borderBottom: '1px solid #E3E4E8' }}>
                执行队列（运行中 {agent.running_commands} + 等待中 {agent.queued_commands} / 最大并发 {maxParallel}）
              </div>
            }
            content={<PendingCommandsContent commands={pendingCommands} onRunClick={(runId) => { setPopoverOpen(false); navigate(`/runs/${runId}`); }} />}
            styles={{ body: { padding: '8px 0', minWidth: 320, maxWidth: 480 } }}
          >
            <span
              role="button"
              tabIndex={hasQueue ? 0 : -1}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                cursor: hasQueue ? 'pointer' : 'default',
                color: hasQueue ? '#3D5BFF' : '#7C7F88',
              }}
            >
              <Activity size={11} />
              运行中 {agent.running_commands} / 等待中 {agent.queued_commands} / 并发 {maxParallel}
            </span>
          </Popover>
          <span style={{ marginLeft: 8, color: '#E3E4E8' }}>|</span>
          <span style={{ marginLeft: 4 }}>{online ? `连接 ${formatTs(agent.connected_at)}` : '未连接'}</span>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Tooltip title="主机详情">
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => { e.stopPropagation(); onShowDetail?.(agent); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); onShowDetail?.(agent); } }}
              style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 24, height: 24, borderRadius: 6, cursor: 'pointer',
                color: '#7C7F88', transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#E3E4E8'; e.currentTarget.style.color = '#121620'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = ''; e.currentTarget.style.color = '#7C7F88'; }}
            >
              <Info size={14} />
            </span>
          </Tooltip>
          {!online && (
            <Tooltip title={agent.net_status === 'unreachable' ? 'TCP 不可达，无法部署' : '部署 agent'}>
              <Popconfirm
                title={`部署 Agent "${agent.agent_id}"?`}
                description={
                  agent.net_status === 'unreachable'
                    ? '主机 TCP 不可达，部署可能失败。是否继续？'
                    : '将在该主机部署并启动 agent，耗时数分钟。'
                }
                okText="部署"
                cancelText="取消"
                disabled={agent.net_status === 'unreachable'}
                onConfirm={(e) => { e?.stopPropagation(); deploy.mutate(agent.agent_id); }}
                onCancel={(e) => e?.stopPropagation()}
              >
                <span
                  role="button"
                  tabIndex={agent.net_status === 'unreachable' ? -1 : 0}
                  onClick={(e) => { e.stopPropagation(); if (agent.net_status === 'unreachable') return; }}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') e.stopPropagation(); }}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 24, height: 24, borderRadius: 6,
                    cursor: agent.net_status === 'unreachable' ? 'not-allowed' : isDeploying ? 'wait' : 'pointer',
                    color: agent.net_status === 'unreachable' ? '#E3E4E8' : '#3D5BFF',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    if (agent.net_status === 'unreachable' || isDeploying) return;
                    e.currentTarget.style.background = 'rgba(126, 173, 255, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    if (agent.net_status === 'unreachable') return;
                    e.currentTarget.style.background = '';
                  }}
                >
                  {isDeploying ? <Loader2 size={13} className="animate-spin" /> : <CloudUpload size={14} />}
                </span>
              </Popconfirm>
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
}

export default memo(ServerCard, (prev, next) => {
  return (
    prev.agent === next.agent &&
    prev.detectedSystem === next.detectedSystem &&
    prev.detectedArch === next.detectedArch &&
    prev.onShowDetail === next.onShowDetail
  );
});
