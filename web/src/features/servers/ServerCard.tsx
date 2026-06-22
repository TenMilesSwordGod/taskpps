import { memo, useState } from 'react';
import { Tooltip, Popconfirm, Tag, Popover } from 'antd';
import type { AgentWithConfig, PendingCommandItem } from '@/types';
import {
  Cpu, Globe, Hash, Activity, Wifi, WifiOff, Plug, Unplug, HelpCircle,
  CloudUpload, Loader2, Info, FolderOpen, ExternalLink,
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
        <Plug size={14} color="#17b26a" />
      </Tooltip>
    );
  }
  if (netStatus === 'unreachable') {
    return (
      <Tooltip title="网络不可达">
        <Unplug size={14} color="#f04438" />
      </Tooltip>
    );
  }
  return (
    <Tooltip title="网络状态未知">
      <HelpCircle size={14} color="#98a2b3" />
    </Tooltip>
  );
}

function formatTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString('zh-CN');
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

function PendingCommandsContent({ commands, onRunClick }: { commands?: PendingCommandItem[]; onRunClick: (runId: string) => void }) {
  if (!commands?.length) {
    return <div style={{ padding: '8px 12px', color: '#98a2b3', fontSize: 12 }}>暂无运行中命令</div>;
  }
  return (
    <div>
      {commands.map((cmd, index) => (
        <div
          key={cmd.command_id}
          style={{ padding: '6px 12px', borderBottom: '1px solid #f2f4f7', fontSize: 12 }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: 4,
                  background: '#eff8ff',
                  color: '#2e90fa',
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
              <span style={{ fontWeight: 600, color: '#1d2939' }}>
                {cmd.task_name || <span style={{ color: '#98a2b3' }}>未知任务</span>}
              </span>
            </span>
            <span style={{ color: '#2e90fa', fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 2 }}>
              <Loader2 size={10} className="animate-spin" />
              {formatDuration(cmd.duration_s)}
            </span>
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#475467', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={cmd.command}>
            {cmd.command || '—'}
          </div>
          {cmd.run_id && (
            <div style={{ marginTop: 3 }}>
              <span
                role="button"
                tabIndex={0}
                onClick={() => onRunClick(cmd.run_id)}
                onKeyDown={(e) => { if (e.key === 'Enter') onRunClick(cmd.run_id); }}
                style={{ fontSize: 11, color: '#2e90fa', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 3 }}
              >
                <ExternalLink size={10} />
                {cmd.run_id.slice(0, 8)}
              </span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ServerCard({ agent, detectedSystem, detectedArch, onShowDetail }: ServerCardProps) {
  const online = agent.connected;
  const deploy = useDeployAgent();
  const navigate = useNavigate();
  const isDeploying = deploy.isPending && deploy.variables === agent.agent_id;
  const [popoverOpen, setPopoverOpen] = useState(false);
  const { data: pendingCommands } = usePendingCommands(agent.agent_id, popoverOpen && agent.running_commands > 0);

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
        background: '#fff',
        border: '1px solid #eaecf0',
        borderLeft: online ? '3px solid #17b26a' : '3px solid #eaecf0',
        borderRadius: '6px 8px 8px 6px',
        padding: '12px 14px',
        transition: 'box-shadow 0.15s, transform 0.15s, border-color 0.15s',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)';
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
            background: '#f9fafb',
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
                color: '#1d2939',
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
              style={{ margin: 0, fontSize: 10, lineHeight: '16px', padding: '0 5px', borderRadius: 4, border: 'none' }}
            >
              {online ? '在线' : '离线'}
            </Tag>
          </div>
          <div style={{ fontSize: 11, color: '#667085', marginTop: 2, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
            <span title={agent.source_file || agent.agent_id}>{agent.agent_id}</span>
            <span style={{ color: '#d0d5dd' }}>·</span>
            <span>{typeLabel}</span>
            {agent.project_id && (
              <>
                <span style={{ color: '#d0d5dd' }}>·</span>
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
            {online ? <Wifi size={14} color="#17b26a" /> : <WifiOff size={14} color="#98a2b3" />}
          </Tooltip>
          <NetStatusIcon netStatus={agent.net_status} />
        </div>
      </div>

      {/* 信息行：简洁双行布局 */}
      <div
        style={{
          background: '#f9fafb',
          borderRadius: 6,
          padding: '8px 10px',
          marginBottom: 8,
        }}
      >
        <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#475467', minWidth: 0 }}>
            <Globe size={11} style={{ flexShrink: 0, color: '#98a2b3' }} />
            <span style={{ fontFamily: 'monospace', fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {displayIp}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#475467', flexShrink: 0 }}>
            <Hash size={11} style={{ flexShrink: 0, color: '#98a2b3' }} />
            <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{versionDisplay}</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 5, fontSize: 12, color: '#475467' }}>
          <Cpu size={11} style={{ flexShrink: 0, color: '#98a2b3' }} />
          <span style={{ fontSize: 12 }}>{osArchText}</span>
        </div>
      </div>

      {/* 底部：运行命令数 / 最大并发 / 连接时间 + 操作按钮 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: '#98a2b3' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Popover
            open={popoverOpen}
            onOpenChange={(open) => setPopoverOpen(open && agent.running_commands > 0)}
            trigger="click"
            placement="topLeft"
            title={
              <div style={{ padding: '6px 12px', fontSize: 12, fontWeight: 600, color: '#1d2939', borderBottom: '1px solid #f2f4f7' }}>
                执行队列（{agent.running_commands} / 最大并发 {maxParallel}）
              </div>
            }
            content={<PendingCommandsContent commands={pendingCommands} onRunClick={(runId) => { setPopoverOpen(false); navigate(`/runs/${runId}`); }} />}
            styles={{ body: { padding: '8px 0', minWidth: 320, maxWidth: 480 } }}
          >
            <span
              role="button"
              tabIndex={agent.running_commands > 0 ? 0 : -1}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                cursor: agent.running_commands > 0 ? 'pointer' : 'default',
                color: agent.running_commands > 0 ? '#2e90fa' : '#98a2b3',
              }}
            >
              <Activity size={11} />
              运行中 {agent.running_commands} / 并发 {maxParallel}
            </span>
          </Popover>
          <span style={{ marginLeft: 8, color: '#d0d5dd' }}>|</span>
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
                color: '#667085', transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#f2f4f7'; e.currentTarget.style.color = '#1d2939'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = ''; e.currentTarget.style.color = '#667085'; }}
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
                    color: agent.net_status === 'unreachable' ? '#d0d5dd' : '#2e90fa',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    if (agent.net_status === 'unreachable' || isDeploying) return;
                    e.currentTarget.style.background = '#eff8ff';
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
