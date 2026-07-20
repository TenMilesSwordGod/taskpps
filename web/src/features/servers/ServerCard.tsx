import { memo, useState, useCallback } from 'react';
import { Tooltip, Popconfirm, Tag, Popover } from 'antd';
import type { AgentWithConfig, PendingCommandItem } from '@/types';
import {
  Cpu, Globe, Hash, Activity, Wifi, WifiOff, Plug, Unplug, HelpCircle,
  CloudUpload, Loader2, Info, ExternalLink, Clock, Timer, Terminal, RefreshCw,
} from 'lucide-react';
import { useDeployAgent, useUpdateDeployAgent, usePendingCommands, useAgentStatus } from '@/api/agents';
import { useNavigate } from 'react-router-dom';
import { RelativeTime } from '@/components/RelativeTime';

interface ServerCardProps {
  agent: AgentWithConfig;
  detectedSystem?: string;
  detectedArch?: string;
  onShowDetail?: (agent: AgentWithConfig) => void;
  onShowRepl?: (agent: AgentWithConfig) => void;
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

function formatRelativeTime(ts: number, now?: number): string {
  if (!ts) return '';
  const diff = Math.floor(((now ?? Date.now()) / 1000) - ts);
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

/** 操作按钮：统一的图标按钮样式 */
function IconBtn({
  icon, title, onClick, disabled, accent, spinIcon,
}: {
  icon: React.ReactNode;
  title: string;
  onClick?: (e: React.MouseEvent) => void;
  disabled?: boolean;
  accent?: boolean;
  spinIcon?: boolean;
}) {
  return (
    <Tooltip title={title}>
      <span
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={(e) => { e.stopPropagation(); if (disabled) return; onClick?.(e); }}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); if (!disabled) onClick?.(e as unknown as React.MouseEvent); } }}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 28, height: 28, borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
          color: disabled ? '#E3E4E8' : accent ? '#3D5BFF' : '#7C7F88',
          transition: 'background 0.15s, color 0.15s',
          opacity: disabled ? 0.6 : 1,
        }}
        onMouseEnter={(e) => { if (!disabled) { e.currentTarget.style.background = accent ? 'rgba(126, 173, 255, 0.1)' : '#F6F6F8'; e.currentTarget.style.color = accent ? '#3D5BFF' : '#121620'; } }}
        onMouseLeave={(e) => { e.currentTarget.style.background = ''; e.currentTarget.style.color = disabled ? '#E3E4E8' : accent ? '#3D5BFF' : '#7C7F88'; }}
      >
        {spinIcon ? <span className="animate-spin" style={{ display: 'inline-flex' }}>{icon}</span> : icon}
      </span>
    </Tooltip>
  );
}

/** 状态点：three 态
 *  - 'syncing'：正在获取该服务器实时信息（呼吸灯，琥珀色）
 *  - 'online' ：已连接（呼吸灯，绿色）
 *  - 'offline'：未连接（静态灰）
 */
type DotState = 'syncing' | 'online' | 'offline';
function StatusDot({ state }: { state: DotState }) {
  const color = state === 'online' ? '#10b981' : state === 'syncing' ? '#F59E0B' : '#C9CBD3';
  const glow = state === 'online'
    ? '0 0 6px rgba(16, 185, 129, 0.45)'
    : state === 'syncing'
      ? '0 0 6px rgba(245, 158, 11, 0.5)'
      : 'none';
  const shouldPulse = state !== 'offline';
  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 8, height: 8 }}>
      {shouldPulse && (
        <span
          style={{
            position: 'absolute', width: 8, height: 8, borderRadius: '50%',
            background: color, opacity: 0.35,
            animation: 'serverDotPulse 1.8s ease-out infinite',
          }}
        />
      )}
      <span
        style={{
          width: 8, height: 8, borderRadius: '50%',
          background: color,
          boxShadow: glow,
          position: 'relative', zIndex: 1,
          // 绿↔灰切换时柔和过渡，避免硬切造成闪烁
          transition: 'background-color 0.45s ease, box-shadow 0.45s ease',
        }}
      />
      <style>{`
        @keyframes serverDotPulse {
          0% { transform: scale(1); opacity: 0.35; }
          70% { transform: scale(2.2); opacity: 0; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes serverDotPulse { 0%,100% { opacity: 0; } }
        }
      `}</style>
    </span>
  );
}

function ServerCard({ agent, detectedSystem, detectedArch, onShowDetail, onShowRepl }: ServerCardProps) {
  // 每卡独立拉取实时状态：谁先回来谁先点亮，不再等整批都好才一起显示
  const liveQuery = useAgentStatus(agent.agent_id);
  const live = liveQuery.data;
  // 仅在"尚无任何实时数据"时显示获取中（呼吸灯变黄）；稳态后台刷新时保持当前
  // 绿/灰状态安静更新，避免每 5s 闪一下黄再变绿造成抖动。
  const hasLive = !!live;
  const syncing = !hasLive && (liveQuery.isLoading || liveQuery.isFetching);
  const deploy = useDeployAgent();
  const updateDeploy = useUpdateDeployAgent();
  const navigate = useNavigate();
  const isDeploying = deploy.isPending && deploy.variables === agent.agent_id;
  const isUpdating = updateDeploy.isPending && updateDeploy.variables === agent.agent_id;
  const isSshAgent = (agent.type || '').startsWith('ssh-');
  const [popoverOpen, setPopoverOpen] = useState(false);
  // 实时字段优先用每卡拉取的结果，未回来前回退到列表快照（老数据）
  const online = hasLive ? live!.connected : agent.connected;
  const hasQueue = (hasLive ? live!.running_commands : agent.running_commands) > 0
    || (hasLive ? live!.queued_commands : agent.queued_commands) > 0;
  const { data: pendingCommands } = usePendingCommands(agent.agent_id, popoverOpen && hasQueue);

  const effectiveSystem = detectedSystem
    || (hasLive && live!.system) || agent.system
    || fallbackSystem(agent.type);
  const effectiveArch = detectedArch
    || (hasLive && live!.arch) || agent.arch
    || fallbackArch();
  const osIcon = getOsIcon(effectiveSystem);
  const systemLabel = effectiveSystem ? getSystemLabel(effectiveSystem) : '—';
  const archLabel = effectiveArch ? getArchLabel(effectiveArch) : '—';
  const typeLabel = getTypeLabel(agent.type);

  const displayName = agent.name || agent.hostname || agent.agent_id;
  const liveIp = hasLive && live!.ip ? live!.ip : '';
  const displayIp = liveIp || agent.ip || (agent.host ? (agent.port ? `${agent.host}:${agent.port}` : agent.host) : '—');
  const liveVersion = hasLive && live!.agent_version ? live!.agent_version : '';
  const versionDisplay = liveVersion ? `v${liveVersion}` : (agent.agent_version ? `v${agent.agent_version}` : '—');
  const osArchText = osArchLabel(systemLabel, archLabel);
  const maxParallel = (hasLive ? live!.max_parallel : agent.max_parallel) ?? 1;
  const connectedAt = hasLive && live!.connected_at ? live!.connected_at : agent.connected_at;
  const deployDisabled = !online && agent.net_status === 'unreachable';
  // 最近更新时间：每卡状态拉取完成时刻（dataUpdatedAt 为 ms）
  const lastUpdatedAt = liveQuery.dataUpdatedAt || undefined;

  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E3E4E8',
        borderRadius: 8,
        padding: '14px 16px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        position: 'relative',
        overflow: 'hidden',
        transition: 'box-shadow 0.22s cubic-bezier(0.76, 0, 0.24, 1), transform 0.22s cubic-bezier(0.76, 0, 0.24, 1), border-color 0.22s cubic-bezier(0.76, 0, 0.24, 1)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = 'rgba(17, 26, 74, 0.1) 0px 1px 3px 0px';
        e.currentTarget.style.transform = 'translateY(-1px)';
        e.currentTarget.style.borderColor = online ? 'rgba(16, 185, 129, 0.4)' : '#C9CBD3';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '';
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.borderColor = '#E3E4E8';
      }}
    >
      {/* 顶部：图标 + 名称 + 状态指示 */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 8,
            background: '#F6F6F8',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            opacity: online ? 1 : 0.55,
            transition: 'opacity 0.22s',
          }}
        >
          <img src={osIcon} alt="" style={{ width: 24, height: 24, objectFit: 'contain' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: online ? '#121620' : '#7C7F88',
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
          <div style={{ fontSize: 11, color: '#7C7F88', marginTop: 3, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
            <span title={agent.source_file || agent.agent_id}>{agent.agent_id}</span>
            <span style={{ color: '#E3E4E8' }}>·</span>
            <span>{typeLabel}</span>

          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexShrink: 0, paddingTop: 4 }}>
          <StatusDot state={syncing ? 'syncing' : online ? 'online' : 'offline'} />
          <Tooltip title={syncing ? '正在获取实时状态…' : online ? 'Agent 已连接' : 'Agent 未连接'}>
            {syncing ? <Loader2 size={14} className="animate-spin" color="#F59E0B" />
              : online ? <Wifi size={14} color="#10b981" /> : <WifiOff size={14} color="#C9CBD3" />}
          </Tooltip>
          <NetStatusIcon netStatus={agent.net_status} />
        </div>
      </div>

      {/* 信息区：标签 + 值，规整两行 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', rowGap: 7, columnGap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <Globe size={11} style={{ flexShrink: 0, color: '#9CA0AC' }} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#121620', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {displayIp}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Hash size={11} style={{ flexShrink: 0, color: '#9CA0AC' }} />
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#121620' }}>{versionDisplay}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, gridColumn: '1 / -1' }}>
          <Cpu size={11} style={{ flexShrink: 0, color: '#9CA0AC' }} />
          <span style={{ fontSize: 12, color: '#121620' }}>{osArchText}</span>
        </div>
      </div>

      {/* 上次执行时间 */}
      <LastExecTime timestamp={agent.last_execution_time} />

      {/* 底部分隔线 + 队列/操作 */}
      <div style={{ borderTop: '1px solid #F0F1F3', paddingTop: 9, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, flex: 1 }}>
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
                color: hasQueue ? '#3D5BFF' : '#9CA0AC',
                fontSize: 11,
                whiteSpace: 'nowrap',
              }}
            >
              <Activity size={11} />
              运行中 {hasLive ? live!.running_commands : agent.running_commands} / 等待中 {hasLive ? live!.queued_commands : agent.queued_commands} / 并发 {maxParallel}
            </span>
          </Popover>
          <span style={{ color: '#E3E4E8', fontSize: 11 }}>|</span>
          <span style={{ fontSize: 11, color: '#9CA0AC', whiteSpace: 'nowrap' }}>
            {syncing
              ? '获取中…'
              : online
                ? `连接 ${formatTs(connectedAt)}`
                : '未连接'}
          </span>
          {lastUpdatedAt && (
            <>
              <span style={{ color: '#E3E4E8', fontSize: 11 }}>|</span>
              <RelativeTime
                tsMs={lastUpdatedAt}
                prefix="更新于"
                style={{ fontSize: 11, color: '#9CA0AC', whiteSpace: 'nowrap' }}
              />
            </>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, flexShrink: 0 }}>
          <IconBtn
            icon={<Terminal size={15} />}
            title={online ? 'Web REPL — 执行命令（不占用并发）' : 'Agent 离线，无法执行'}
            disabled={!online}
            accent
            onClick={() => onShowRepl?.(agent)}
          />
          <IconBtn
            icon={<Info size={15} />}
            title="主机详情"
            onClick={() => onShowDetail?.(agent)}
          />
          {online && isSshAgent && (
            <Popconfirm
              title={`更新部署 Agent "${agent.agent_id}"？`}
              description="将重新上传最新二进制并重启 agent 进程，耗时数分钟。"
              okText="更新部署"
              cancelText="取消"
              onConfirm={(e) => { e?.stopPropagation(); updateDeploy.mutate(agent.agent_id); }}
              onCancel={(e) => e?.stopPropagation()}
            >
              <IconBtn
                icon={isUpdating ? <Loader2 size={15} /> : <RefreshCw size={15} />}
                title={isUpdating ? '更新部署中...' : '更新部署（重新上传二进制并重启）'}
                disabled={isUpdating}
                accent
                spinIcon={isUpdating}
              />
            </Popconfirm>
          )}
          {!online && (
            <Popconfirm
              title={`部署 Agent "${agent.agent_id}"?`}
              description={
                deployDisabled
                  ? '主机 TCP 不可达，部署可能失败。是否继续？'
                  : '将在该主机部署并启动 agent，耗时数分钟。'
              }
              okText="部署"
              cancelText="取消"
              disabled={deployDisabled}
              onConfirm={(e) => { e?.stopPropagation(); deploy.mutate(agent.agent_id); }}
              onCancel={(e) => e?.stopPropagation()}
            >
              <IconBtn
                icon={isDeploying ? <Loader2 size={15} /> : <CloudUpload size={15} />}
                title={deployDisabled ? 'TCP 不可达，无法部署' : '部署 agent'}
                disabled={deployDisabled || isDeploying}
                accent
                spinIcon={isDeploying}
              />
            </Popconfirm>
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
    prev.onShowDetail === next.onShowDetail &&
    prev.onShowRepl === next.onShowRepl
  );
});
