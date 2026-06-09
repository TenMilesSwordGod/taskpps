import { Modal, Spin, Progress, Tag, Alert, Empty, Button } from 'antd';
import {
  Cpu, MemoryStick, HardDrive, Server, Activity, AlertCircle, RefreshCw,
  Layers, MonitorSmartphone, Box, Hash, Clock,
} from 'lucide-react';
import type { AgentHostInfo, AgentWithConfig, DiskInfo } from '@/types';
import { useAgentHostInfo } from '@/api/agents';

interface Props {
  open: boolean;
  agent: AgentWithConfig | null;
  onClose: () => void;
}

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

interface InfoRowProps {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}
function InfoRow({ icon, label, value }: InfoRowProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: '1px solid #f3f4f6' }}>
      <div style={{ width: 28, height: 28, borderRadius: 6, background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280', flexShrink: 0 }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: '#9ca3af', lineHeight: 1.2 }}>{label}</div>
        <div style={{ fontSize: 13, color: '#111827', lineHeight: 1.4, marginTop: 2, wordBreak: 'break-word' }}>{value}</div>
      </div>
    </div>
  );
}

function DiskRow({ disk }: { disk: DiskInfo }) {
  const pct = disk.percent < 0 ? 0 : disk.percent;
  return (
    <div style={{ padding: '8px 10px', borderRadius: 6, background: '#fafafa', marginBottom: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
        <span style={{ fontFamily: 'monospace', color: '#374151' }} title={disk.mount}>
          {disk.mount}
        </span>
        <span style={{ color: '#6b7280', fontSize: 11 }}>
          {disk.used} / {disk.size}（{disk.avail} 可用）
        </span>
      </div>
      <Progress
        percent={pct}
        size="small"
        showInfo={false}
        strokeColor={getPercentColor(pct)}
        trailColor="#e5e7eb"
      />
    </div>
  );
}

export default function HostInfoModal({ open, agent, onClose }: Props) {
  const { data, isLoading, isError, error, refetch, isRefetching } = useAgentHostInfo(open ? agent?.agent_id ?? null : null);

  const sourceLabel = data?.source === 'ssh' ? 'SSH 探测' : data?.source === 'agent' ? 'Agent 上报' : '本地';

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={720}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Server size={18} color="#6b7280" />
          <span style={{ fontSize: 16, fontWeight: 600 }}>Agent Host 详情</span>
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
          type="error"
          showIcon
          message={`获取 host 信息失败 (HTTP ${(error as any)?.status || '???'})`}
          description={
            <div>
              <div>{(error as any)?.detail ?? (error as Error)?.message ?? '未知错误'}</div>
              <div style={{ marginTop: 12, padding: 10, background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 4, fontSize: 12 }}>
                <div style={{ fontWeight: 600, marginBottom: 4, color: '#92400e' }}>后端可能还在跑旧代码？</div>
                <div style={{ color: '#78350f' }}>本次修复需要重启 taskpps 服务才能生效。在服务器执行：</div>
                <code style={{ display: 'block', marginTop: 4, padding: 6, background: '#fffbeb', borderRadius: 3, color: '#1f2937', fontFamily: 'monospace' }}>
                  sudo /opt/taskpps/scripts/hotupdate.sh
                </code>
                <div style={{ marginTop: 4, color: '#78350f' }}>（热重载 gunicorn，保留运行中 pipeline）</div>
              </div>
            </div>
          }
          action={
            <Button size="small" onClick={() => refetch()}>重试</Button>
          }
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

          {/* 系统信息 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px', marginBottom: 16 }}>
            <div>
              <InfoRow
                icon={<MonitorSmartphone size={14} />}
                label="系统 / 发行版"
                value={<span style={{ fontFamily: 'monospace' }}>{getOsShortLabel(data.os_release, data.kernel.split(' ')[0] || '')}</span>}
              />
              <InfoRow icon={<Layers size={14} />} label="内核" value={<span style={{ fontFamily: 'monospace', fontSize: 12 }}>{data.kernel || '—'}</span>} />
              <InfoRow icon={<Clock size={14} />} label="运行时间" value={<span style={{ fontFamily: 'monospace' }}>{data.uptime || '—'}</span>} />
            </div>
            <div>
              <InfoRow icon={<Box size={14} />} label="主机名" value={<span style={{ fontFamily: 'monospace' }}>{data.hostname || '—'}</span>} />
              <InfoRow
                icon={<Hash size={14} />}
                label="Agent ID"
                value={<span style={{ fontFamily: 'monospace' }}>{data.agent_id}</span>}
              />
              {agent && (
                <InfoRow
                  icon={<Server size={14} />}
                  label="连接地址"
                  value={<span style={{ fontFamily: 'monospace' }}>{agent.host}:{agent.port}</span>}
                />
              )}
            </div>
          </div>

          {/* CPU */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Cpu size={16} color="#2563eb" />
              <span style={{ fontWeight: 600, fontSize: 13 }}>CPU</span>
              {data.cpu.threads > 0 && (
                <Tag color="blue" style={{ marginLeft: 'auto' }}>
                  {data.cpu.cores > 0 ? `${data.cpu.cores} 核 / ` : ''}{data.cpu.threads} 线程
                </Tag>
              )}
            </div>
            <div style={{ fontSize: 12, color: '#4b5563', fontFamily: 'monospace', wordBreak: 'break-word' }}>
              {data.cpu.model || '—'}
            </div>
          </div>

          {/* 内存 */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <MemoryStick size={16} color="#a855f7" />
              <span style={{ fontWeight: 600, fontSize: 13 }}>内存</span>
              {data.memory.percent >= 0 && (
                <Tag color="purple" style={{ marginLeft: 'auto' }}>{data.memory.percent}% 已用</Tag>
              )}
            </div>
            {data.memory.percent >= 0 ? (
              <Progress
                percent={data.memory.percent}
                strokeColor={getPercentColor(data.memory.percent)}
                trailColor="#e5e7eb"
              />
            ) : (
              <div style={{ height: 8, background: '#e5e7eb', borderRadius: 4 }} />
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginTop: 6, fontFamily: 'monospace' }}>
              <span>已用 {data.memory.used || '—'}</span>
              <span>可用 {data.memory.free || '—'}</span>
              <span>总计 {data.memory.total || '—'}</span>
            </div>
          </div>

          {/* 磁盘 */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <HardDrive size={16} color="#10b981" />
              <span style={{ fontWeight: 600, fontSize: 13 }}>磁盘</span>
              <Tag style={{ marginLeft: 'auto' }}>{data.disks.length} 个挂载点</Tag>
            </div>
            {data.disks.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无磁盘信息" />
            ) : (
              data.disks.map((d, i) => <DiskRow key={i} disk={d} />)
            )}
          </div>

          {/* 底部操作 */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
            <Button icon={isRefetching ? <Activity size={14} className="animate-spin" /> : <RefreshCw size={14} />} onClick={() => refetch()} loading={isRefetching} size="small">
              重新探测
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
