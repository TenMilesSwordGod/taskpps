import { useState } from 'react';
import { Modal, Spin, Tag, Alert, Empty, Button } from 'antd';
import {
  Cpu, MemoryStick, HardDrive, Server, Activity, AlertCircle, RefreshCw,
  MonitorSmartphone, ChevronDown, ChevronRight,
} from 'lucide-react';
import type { AgentWithConfig, DiskInfo } from '@/types';
import { useAgentHostInfo } from '@/api/agents';

interface Props {
  open: boolean;
  agent: AgentWithConfig | null;
  onClose: () => void;
}

/** 磁盘折叠阈值：超过则默认折叠，点击展开 */
const DISK_COLLAPSE_THRESHOLD = 6;
const DISK_COLLAPSE_SHOW = 5;

function getOsShortLabel(osRelease: string, system: string): string {
  if (osRelease) {
    const match = osRelease.match(/^PRETTY_NAME="?([^"\n]+)"?/m);
    if (match) return match[1];
  }
  if (system) return system;
  return '—';
}

function getPercentColor(p: number): string {
  if (p < 0) return '#9ca3af';
  if (p < 60) return '#10b981';
  if (p < 85) return '#f59e0b';
  return '#ef4444';
}

/** 分区标题：小标签 + 右侧可选附加，下方 hairline 分隔 */
function SectionHeader({
  icon, label, extra,
}: { icon: React.ReactNode; label: string; extra?: React.ReactNode }) {
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginTop: 16, marginBottom: 8, paddingBottom: 6,
        borderBottom: '1px solid #e5e7eb',
      }}
    >
      <span style={{ display: 'inline-flex', color: '#6b7280' }}>{icon}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: '#374151', letterSpacing: 0.3 }}>{label}</span>
      <span style={{ marginLeft: 'auto' }}>{extra}</span>
    </div>
  );
}

/** 系统信息行：label + value 紧凑双列 */
function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '4px 0', fontSize: 12 }}>
      <span style={{ color: '#9ca3af', width: 72, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#111827', fontFamily: 'monospace', wordBreak: 'break-word', minWidth: 0 }}>{value}</span>
    </div>
  );
}

/** 紧凑磁盘行：挂载点 | 使用率细条 | 已用/总量 */
function DiskRow({ disk }: { disk: DiskInfo }) {
  const pct = disk.percent < 0 ? 0 : disk.percent;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0' }}>
      <span
        title={disk.mount}
        style={{
          fontFamily: 'monospace', fontSize: 12, color: '#374151',
          width: 120, flexShrink: 0, whiteSpace: 'nowrap',
          overflow: 'hidden', textOverflow: 'ellipsis',
        }}
      >
        {disk.mount}
      </span>
      {/* 使用率细条 */}
      <div style={{ flex: 1, height: 6, background: '#f3f4f6', borderRadius: 3, overflow: 'hidden', minWidth: 60 }}>
        <div
          style={{
            width: `${pct}%`, height: '100%',
            background: getPercentColor(pct), borderRadius: 3,
            transition: 'width 0.2s',
          }}
        />
      </div>
      <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#6b7280', flexShrink: 0, textAlign: 'right' }}>
        {disk.used} / {disk.size}
      </span>
      <span style={{ fontSize: 11, width: 34, flexShrink: 0, textAlign: 'right', color: getPercentColor(pct) }}>
        {disk.percent >= 0 ? `${pct}%` : '—'}
      </span>
    </div>
  );
}

export default function HostInfoModal({ open, agent, onClose }: Props) {
  const { data, isLoading, isError, refetch, isRefetching } = useAgentHostInfo(open ? agent?.agent_id ?? null : null);
  const [diskExpanded, setDiskExpanded] = useState(false);

  const sourceLabel = data?.source === 'ssh' ? 'SSH 探测' : data?.source === 'agent' ? 'Agent 上报' : '本地';

  // 磁盘折叠逻辑
  const allDisks = data?.disks ?? [];
  const hasManyDisks = allDisks.length > DISK_COLLAPSE_THRESHOLD;
  const visibleDisks = hasManyDisks && !diskExpanded
    ? allDisks.slice(0, DISK_COLLAPSE_SHOW)
    : allDisks;
  const hiddenCount = allDisks.length - DISK_COLLAPSE_SHOW;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={680}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Server size={18} color="#6b7280" />
          <span style={{ fontSize: 15, fontWeight: 600 }}>主机详情</span>
          {agent && (
            <Tag color={agent.connected ? 'green' : 'default'} style={{ marginLeft: 4 }}>
              {agent.connected ? '在线' : '离线'}
            </Tag>
          )}
          <Tag style={{ marginLeft: 0 }}>{sourceLabel}</Tag>
        </div>
      }
    >
      {isLoading && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 60 }}>
          <Spin tip="探测中…" size="large" />
        </div>
      )}

      {isError && (
        <Alert
          type="warning"
          showIcon
          message="主机信息暂不可用"
          description="后端探测失败，请稍后重试或联系管理员。"
          action={<Button size="small" onClick={() => refetch()}>重试</Button>}
        />
      )}

      {data && !isLoading && (
        <>
          {data.error && (
            <Alert
              type="warning"
              showIcon
              icon={<AlertCircle size={16} />}
              message="部分信息不可用"
              description={data.error}
              style={{ marginBottom: 12 }}
            />
          )}

          {/* 系统信息 — 双列紧凑布局 */}
          <SectionHeader icon={<MonitorSmartphone size={14} />} label="系统" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px' }}>
            <div>
              <InfoRow label="发行版" value={getOsShortLabel(data.os_release, data.kernel.split(' ')[0] || '')} />
              <InfoRow label="内核" value={data.kernel || '—'} />
              <InfoRow label="运行时间" value={data.uptime || '—'} />
            </div>
            <div>
              <InfoRow label="主机名" value={data.hostname || '—'} />
              <InfoRow label="Agent ID" value={data.agent_id} />
              {agent && (
                <InfoRow label="连接地址" value={`${agent.host}:${agent.port}`} />
              )}
            </div>
          </div>

          {/* CPU */}
          <SectionHeader
            icon={<Cpu size={14} />}
            label="CPU"
            extra={data.cpu.threads > 0 ? (
              <Tag color="blue" style={{ margin: 0 }}>
                {data.cpu.cores > 0 ? `${data.cpu.cores} 核 / ` : ''}{data.cpu.threads} 线程
              </Tag>
            ) : null}
          />
          <div style={{ fontSize: 12, color: '#4b5563', fontFamily: 'monospace', wordBreak: 'break-word', padding: '4px 0' }}>
            {data.cpu.model || '—'}
          </div>

          {/* 内存 */}
          <SectionHeader
            icon={<MemoryStick size={14} />}
            label="内存"
            extra={data.memory.percent >= 0 ? (
              <Tag color="purple" style={{ margin: 0 }}>{data.memory.percent}% 已用</Tag>
            ) : null}
          />
          {data.memory.percent >= 0 ? (
            <div style={{ padding: '4px 0' }}>
              <div style={{ height: 6, background: '#f3f4f6', borderRadius: 3, overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${data.memory.percent}%`, height: '100%',
                    background: getPercentColor(data.memory.percent), borderRadius: 3,
                  }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#6b7280', marginTop: 4, fontFamily: 'monospace' }}>
                <span>已用 {data.memory.used || '—'}</span>
                <span>可用 {data.memory.free || '—'}</span>
                <span>总计 {data.memory.total || '—'}</span>
              </div>
            </div>
          ) : (
            <div style={{ height: 6, background: '#f3f4f6', borderRadius: 3, margin: '4px 0' }} />
          )}

          {/* 磁盘 */}
          <SectionHeader
            icon={<HardDrive size={14} />}
            label="磁盘"
            extra={<Tag style={{ margin: 0 }}>{allDisks.length} 个挂载点</Tag>}
          />
          {allDisks.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无磁盘信息" />
          ) : (
            <>
              {visibleDisks.map((d, i) => <DiskRow key={i} disk={d} />)}
              {hasManyDisks && !diskExpanded && (
                <button
                  onClick={() => setDiskExpanded(true)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    marginTop: 4, padding: '4px 0',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: '#2563eb', fontSize: 12,
                  }}
                >
                  <ChevronRight size={12} />
                  展开剩余 {hiddenCount} 个挂载点
                </button>
              )}
              {hasManyDisks && diskExpanded && (
                <button
                  onClick={() => setDiskExpanded(false)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    marginTop: 4, padding: '4px 0',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: '#2563eb', fontSize: 12,
                  }}
                >
                  <ChevronDown size={12} />
                  收起
                </button>
              )}
            </>
          )}

          {/* 底部操作 */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12, paddingTop: 8, borderTop: '1px solid #f3f4f6' }}>
            <Button
              icon={isRefetching ? <Activity size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              onClick={() => refetch()}
              loading={isRefetching}
              size="small"
            >
              重新探测
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
