import { Tooltip } from 'antd';
import type { AgentWithConfig } from '@/types';
import { Cpu, Globe, Hash, Activity, Wifi, WifiOff } from 'lucide-react';

interface ServerCardProps {
  agent: AgentWithConfig;
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
  if (!type) return 'unknown';
  if (type.startsWith('ssh-')) return 'SSH';
  if (type === 'local') return 'Local';
  if (type === 'agent') return 'Agent';
  return type;
}

/** 把时间戳格式化为 hh:mm:ss */
function formatTs(ts: number): string {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleTimeString('zh-CN');
}

export default function ServerCard({ agent }: ServerCardProps) {
  const online = agent.connected;

  // 系统图标：优先按 system 字段，否则按 host 类型兜底
  const osIcon = getOsIcon(agent.system, agent.arch, agent.type);
  const systemLabel = getSystemLabel(agent.system);
  const archLabel = getArchLabel(agent.arch);
  const typeLabel = getTypeLabel(agent.type);

  // 显示名称优先级：yaml.name → agent.hostname（agent 报告的）→ agent_id
  const displayName = agent.name || agent.hostname || agent.agent_id;
  // IP 优先级：agent 报告的真实 IP → yaml 配置 host
  const displayIp = agent.ip || (agent.host ? (agent.port ? `${agent.host}:${agent.port}` : agent.host) : '—');
  // Arch + System 离线兜底
  const archDisplay = agent.arch ? archLabel : '—';
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
        {online ? (
          <Wifi size={16} color="#10b981" />
        ) : (
          <WifiOff size={16} color="#9ca3af" />
        )}
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
