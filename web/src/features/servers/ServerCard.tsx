import { memo } from 'react';
import { Tooltip, Popconfirm } from 'antd';
import type { AgentWithConfig } from '@/types';
import { Cpu, Globe, Hash, Activity, Wifi, WifiOff, Plug, Unplug, HelpCircle, CloudUpload, Loader2 } from 'lucide-react';
import { useDeployAgent } from '@/api/agents';

interface ServerCardProps {
  agent: AgentWithConfig;
  /** 探测后的 system/arch 覆盖（来自 POST /api/agents/check） */
  detectedSystem?: string;
  detectedArch?: string;
}

/** 把 system 字段映射到图标（Linux/Darwin/Windows/...） */
function getOsIcon(system: string, arch: string, type: string): string {
  void type;
  const s = (system || '').toLowerCase();
  if (s.includes('linux')) return '/static/servers/linux.svg';
  if (s.includes('darwin') || s.includes('macos') || s.includes('mac os') || s.includes('apple')) return '/static/servers/apple.svg';
  if (s.includes('windows')) return '/static/servers/windows.svg';
  void arch;
  // 通用 server 图标
  return '/static/servers/server.svg';
}

/** 把 system 字段规整为友好的系统名称 */
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

/** 把 arch 字段规整为友好名称 */
function getArchLabel(arch: string): string {
  const a = (arch || '').toLowerCase();
  if (!a) return 'Unknown';
  if (a.includes('x86_64') || a.includes('amd64')) return 'x86_64';
  if (a.includes('aarch64') || a.includes('arm64')) return 'ARM64';
  if (a.includes('i386') || a.includes('i686') || a === 'x86') return 'x86';
  if (a.includes('armv7') || a.includes('armv6')) return 'ARM';
  return arch;
}

/** 把 type 字段规整为友好名称 */
function getTypeLabel(type: string): string {
  if (!type) return 'Local';
  if (type.startsWith('ssh-')) return 'SSH';
  if (type === 'local') return 'Local';
  if (type === 'execution-agent' || type === 'agent' || type === 'websocket') return 'Agent';
  return type;
}

/** 按 type 字段兜底推导 system（用于离线 / 未探测时显示） */
function fallbackSystem(type: string): string {
  if (!type) return 'Local';
  if (type.startsWith('ssh-')) return 'Linux';
  if (type === 'local') return 'Local';
  if (type === 'execution-agent' || type === 'agent' || type === 'websocket') return '';
  return '';
}

/** 按 type 字段兜底推导 arch：架构是未知的，硬编码 x86_64 是错的，返回空让 UI 显示 "—" */
function fallbackArch(type: string): string {
  return '';
}

/** 网络可达性图标 */
function NetStatusIcon({ netStatus }: { netStatus: 'unknown' | 'reachable' | 'unreachable' }) {
  if (netStatus === 'reachable') {
    return (
      <Tooltip title="网络可达：TCP 端口可连接">
        <Plug size={16} color="#10b981" />
      </Tooltip>
    );
  }
  if (netStatus === 'unreachable') {
    return (
      <Tooltip title="网络不可达：TCP 端口无法连接">
        <Unplug size={16} color="#ef4444" />
      </Tooltip>
    );
  }
  return (
    <Tooltip title="网络状态未知：未配置 host:port">
      <HelpCircle size={16} color="#9ca3af" />
    </Tooltip>
  );
}

/** 把时间戳格式化为 hh:mm:ss */
function formatTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString('zh-CN');
}

function ServerCard({ agent, detectedSystem, detectedArch }: ServerCardProps) {
  const online = agent.connected;
  const deploy = useDeployAgent();
  const isDeploying = deploy.isPending && deploy.variables === agent.agent_id;

  // 优先级：detected > real > type 兜底
  const effectiveSystem = detectedSystem || agent.system || fallbackSystem(agent.type);
  const effectiveArch = detectedArch || agent.arch || fallbackArch(agent.type);
  const fallbackSys = fallbackSystem(agent.type);
  const osIcon = getOsIcon(effectiveSystem, effectiveArch, agent.type);
  // 空值显示 "—"，避免出现 "Unknown" 让用户以为真的是 unknown
  const systemLabel = effectiveSystem ? getSystemLabel(effectiveSystem) : '—';
  const archLabel = effectiveArch ? getArchLabel(effectiveArch) : '—';
  const typeLabel = getTypeLabel(agent.type);

  // 显示名称优先级：yaml.name → agent.hostname（agent 报告的）→ agent_id
  const displayName = agent.name || agent.hostname || agent.agent_id;
  // IP 优先级：agent 报告的真实 IP → yaml 配置 host
  const displayIp = agent.ip || (agent.host ? (agent.port ? `${agent.host}:${agent.port}` : agent.host) : '—');
  // Arch + System 离线兜底（label 已含 '—' 兜底）
  const archDisplay = archLabel;
  const versionDisplay = agent.agent_version ? `v${agent.agent_version}` : '—';

  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        padding: 16,
        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
        transition: 'box-shadow 0.2s, transform 0.2s',
        position: 'relative',
        opacity: online ? 1 : 0.85,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
        e.currentTarget.style.transform = 'translateY(-1px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,0.04)';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      {/* 顶部：图标 + 名称 + 状态灯 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 8,
            background: '#f3f4f6',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            overflow: 'hidden',
          }}
        >
          <img src={osIcon} alt="OS" style={{ width: 28, height: 28, objectFit: 'contain' }} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: online ? '#111827' : '#6b7280',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={displayName}
            >
              {displayName}
            </span>
            <Tooltip title={online ? '在线' : '离线'}>
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: online ? '#10b981' : '#9ca3af',
                  boxShadow: online ? '0 0 0 3px rgba(16,185,129,0.18)' : 'none',
                  flexShrink: 0,
                }}
              />
            </Tooltip>
          </div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
            <Tooltip title={agent.source_file || agent.agent_id}>
              <span>{agent.agent_id}</span>
            </Tooltip>
            {typeLabel !== 'unknown' && (
              <span style={{ marginLeft: 6, color: '#9ca3af' }}>· {typeLabel}</span>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <Tooltip title={online ? 'Agent WS 已连接' : 'Agent WS 未连接'}>
            {online ? (
              <Wifi size={16} color="#10b981" />
            ) : (
              <WifiOff size={16} color="#9ca3af" />
            )}
          </Tooltip>
          <NetStatusIcon netStatus={agent.net_status} />
          {/* 未连接 agent 显示部署按钮（已连接无需部署） */}
          {!online && (
            <Popconfirm
              title={`部署 Agent "${agent.agent_id}"?`}
              description="将通过 bootstrap 流程在该 host 部署并启动 agent。期间将消耗数分钟，请耐心等待。"
              okText="开始部署"
              cancelText="取消"
              onConfirm={(e) => {
                e?.stopPropagation();
                deploy.mutate(agent.agent_id);
              }}
              onCancel={(e) => e?.stopPropagation()}
            >
              <Tooltip title="部署 agent 到此 host">
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') e.stopPropagation();
                  }}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 22,
                    height: 22,
                    borderRadius: 4,
                    cursor: isDeploying ? 'wait' : 'pointer',
                    background: '#eff6ff',
                    color: '#2563eb',
                    border: '1px solid #bfdbfe',
                    transition: 'background 0.15s, border-color 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    if (!isDeploying) {
                      e.currentTarget.style.background = '#dbeafe';
                      e.currentTarget.style.borderColor = '#60a5fa';
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = '#eff6ff';
                    e.currentTarget.style.borderColor = '#bfdbfe';
                  }}
                >
                  {isDeploying ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <CloudUpload size={13} />
                  )}
                </span>
              </Tooltip>
            </Popconfirm>
          )}
        </div>
      </div>

      {/* 信息行：IP / Agent Version / System / Arch */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px', fontSize: 12 }}>
        <Tooltip title="IP 地址">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: online ? '#4b5563' : '#9ca3af' }}>
            <Globe size={12} color="#9ca3af" />
            <span style={{ fontFamily: 'monospace' }}>{displayIp}</span>
          </div>
        </Tooltip>
        <Tooltip title="Agent 版本">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: online ? '#4b5563' : '#9ca3af' }}>
            <Hash size={12} color="#9ca3af" />
            <span style={{ fontFamily: 'monospace' }}>{versionDisplay}</span>
          </div>
        </Tooltip>
        <Tooltip title="操作系统">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: online ? '#4b5563' : '#9ca3af' }}>
            <img src={osIcon} alt="" style={{ width: 12, height: 12, opacity: 0.7 }} />
            <span>{systemLabel}</span>
          </div>
        </Tooltip>
        <Tooltip title="CPU 架构">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: online ? '#4b5563' : '#9ca3af' }}>
            <Cpu size={12} color="#9ca3af" />
            <span style={{ fontFamily: 'monospace' }}>{archDisplay}</span>
          </div>
        </Tooltip>
      </div>

      {/* 底部：运行命令数 / 连接时间 */}
      <div
        style={{
          marginTop: 12,
          paddingTop: 10,
          borderTop: '1px dashed #e5e7eb',
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 11,
          color: '#9ca3af',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <Activity size={11} />
          运行中 {agent.running_commands}
        </span>
        <span>{online ? `连接 ${formatTs(agent.connected_at)}` : '未连接'}</span>
      </div>
    </div>
  );
}

// 用 React.memo 包裹：props 不变时跳过 re-render（react-query 5s refetch 时只更新变化项）
// 自定义比较：detected* 字符串是简单值，可走默认浅比较
export default memo(ServerCard, (prev, next) => {
  return (
    prev.agent === next.agent &&
    prev.detectedSystem === next.detectedSystem &&
    prev.detectedArch === next.detectedArch
  );
});
