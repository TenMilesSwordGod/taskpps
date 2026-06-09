import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { Input, Empty, Tag, Spin, Badge, Tooltip, Alert } from 'antd';
import { Search, Server, RefreshCw, AlertCircle, Radar } from 'lucide-react';
import { useAgentsWithConfig } from '@/api/agents';
import ServerCard from './ServerCard';
import HostInfoModal from './HostInfoModal';
import apiClient from '@/api/client';
import type { AgentCheckResult, AgentWithConfig } from '@/types';

/** Servers 列表页 */
export default function ServersPage() {
  const { data: agents, isLoading, refetch, isFetching, error } = useAgentsWithConfig();
  const [search, setSearch] = useState('');
  // 探测结果（agent_id → { system, arch }），用于按需覆盖 yaml 兜底
  const [detected, setDetected] = useState<Record<string, { system: string; arch: string }>>({});
  const [probing, setProbing] = useState(false);

  const runProbe = async () => {
    if (!agents || agents.length === 0) return;
    setProbing(true);
    try {
      // 调一次 check，遍历 results 收集 system/arch
      const res = await apiClient.post<{ results: AgentCheckResult[] }>('/api/agents/check', {
        timeout: 5,
      });
      const map: Record<string, { system: string; arch: string }> = {};
      for (const r of res.data?.results ?? []) {
        if (r.system || r.arch) {
          map[r.agent_id] = { system: r.system, arch: r.arch };
        }
      }
      setDetected(map);
    } catch (e) {
      // 静默失败，UI 仍展示 type 兜底
      console.warn('probe failed', e);
    } finally {
      setProbing(false);
    }
  };

  // 自动探测：首次拿到 agents 后异步触发一次，填充 system/arch 真实值
  // ref 防止 StrictMode 双触发或 refetch 重复触发
  const autoProbedRef = useRef(false);
  useEffect(() => {
    if (autoProbedRef.current) return;
    if (!agents || agents.length === 0) return;
    // 至少有一个 agent 的 system/arch 是空才值得触发
    const needsProbe = agents.some((a) => !a.system || !a.arch);
    if (!needsProbe) return;
    autoProbedRef.current = true;
    void runProbe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents]);

  // 调试用：直接 raw fetch 一次，识别是"404 未重启"还是"[] 但确实没配"
  const [debugInfo, setDebugInfo] = useState<{ url: string; status: number; type: string; preview: string } | null>(null);
  const checkDebug = async () => {
    const baseURL = (import.meta.env.VITE_API_BASE_URL as string) ?? '';
    const url = `${baseURL}/api/agents/all`;
    try {
      const res = await fetch(url);
      const text = await res.text();
      let type = 'unknown';
      let preview = text.slice(0, 200);
      try {
        const j = JSON.parse(text);
        type = Array.isArray(j) ? `array(${j.length})` : typeof j;
        if (j && typeof j === 'object' && 'detail' in j) preview = `detail: ${j.detail}`;
      } catch {
        type = 'text';
        preview = text.slice(0, 120);
      }
      setDebugInfo({ url, status: res.status, type, preview });
    } catch (e) {
      setDebugInfo({ url, status: -1, type: 'error', preview: String(e) });
    }
  };

  const filtered = useMemo(() => {
    const list = agents ?? [];
    if (!search) return list;
    const s = search.toLowerCase();
    return list.filter(
      (a) =>
        a.agent_id.toLowerCase().includes(s) ||
        a.hostname.toLowerCase().includes(s) ||
        a.name.toLowerCase().includes(s) ||
        a.ip.toLowerCase().includes(s) ||
        a.host.toLowerCase().includes(s) ||
        a.system.toLowerCase().includes(s) ||
        a.arch.toLowerCase().includes(s) ||
        a.type.toLowerCase().includes(s),
    );
  }, [agents, search]);

  const onlineCount = (agents ?? []).filter((a) => a.connected).length;
  const totalCount = (agents ?? []).length;

  // 按 yaml 文件分组（保持 yaml 内定义顺序）
  const grouped = useMemo(() => {
    const list = filtered;
    const groups: { sourceFile: string; items: AgentWithConfig[] }[] = [];
    const indexMap = new Map<string, number>();
    for (const a of list) {
      const sf = a.source_file || 'unknown';
      let idx = indexMap.get(sf);
      if (idx === undefined) {
        idx = groups.length;
        indexMap.set(sf, idx);
        groups.push({ sourceFile: sf, items: [] });
      }
      groups[idx].items.push(a);
    }
    return groups;
  }, [filtered]);

  // host 详情 modal 状态
  const [detailAgent, setDetailAgent] = useState<AgentWithConfig | null>(null);
  const handleShowDetail = useCallback((agent: AgentWithConfig) => {
    setDetailAgent(agent);
  }, []);
  const handleCloseDetail = useCallback(() => setDetailAgent(null), []);

  return (
    <div className="flex flex-col h-full p-4 gap-3 bg-gray-50">
      {/* 顶部工具栏 */}
      <div className="shrink-0 bg-white rounded-lg border border-gray-200 px-4 py-3 shadow-sm flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Server size={18} className="text-gray-500" />
          <span style={{ fontSize: 18, fontWeight: 600 }}>服务器列表</span>
          <Tag color="default">总计 {totalCount}</Tag>
          {onlineCount > 0 && (
            <Badge color="green" text={<span style={{ color: '#10b981' }}>在线 {onlineCount}</span>} />
          )}
          {totalCount - onlineCount > 0 && (
            <Badge color="gray" text={<span style={{ color: '#6b7280' }}>离线 {totalCount - onlineCount}</span>} />
          )}
        </div>
        <div className="flex items-center gap-2">
          <Input
            allowClear
            prefix={<Search size={14} className="text-gray-400" />}
            placeholder="搜索 ID / 名称 / IP / 系统 / 架构 / 类型"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 280 }}
          />
          <Tooltip title="手动刷新">
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              style={{
                border: '1px solid #d1d5db',
                borderRadius: 6,
                padding: '4px 10px',
                background: '#fff',
                cursor: isFetching ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                color: '#374151',
                fontSize: 13,
              }}
            >
              <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
              刷新
            </button>
          </Tooltip>
          <Tooltip title="主动探测所有 agent 的 system / arch（通过 SSH uname）">
            <button
              onClick={runProbe}
              disabled={probing}
              style={{
                border: '1px solid #722ed1',
                borderRadius: 6,
                padding: '4px 10px',
                background: '#fff',
                cursor: probing ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                color: '#722ed1',
                fontSize: 13,
              }}
            >
              <Radar size={14} className={probing ? 'animate-spin' : ''} />
              {probing ? '探测中…' : '探测 system/arch'}
            </button>
          </Tooltip>
        </div>
      </div>

      {/* 卡片网格 */}
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="p-4 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))' }}>
            {[1, 2, 3, 4].map((i) => <ServerCardSkeleton key={i} />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-4 space-y-3">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span style={{ color: '#6b7280' }}>
                  {totalCount === 0 ? '暂无 agent 配置' : '无匹配的服务器'}
                </span>
              }
            />
            <Alert
              type="warning"
              showIcon
              icon={<AlertCircle size={16} />}
              message="诊断信息"
              description={
                <div className="space-y-1 text-xs">
                  <div>API: <code>GET /api/agents/all</code></div>
                  <div>
                    当前状态：{error ? `前端请求失败（${String(error)}）` : '后端返回空数组'}
                  </div>
                  {debugInfo && (
                    <div className="font-mono text-xs bg-gray-50 p-2 rounded border border-gray-200 mt-1">
                      <div>URL: {debugInfo.url}</div>
                      <div>HTTP {debugInfo.status} · type: {debugInfo.type}</div>
                      <div>preview: {debugInfo.preview}</div>
                    </div>
                  )}
                  <div className="text-gray-500 mt-2">
                    可能原因：
                    <ul className="list-disc pl-5 mt-1">
                      <li>后端 Python 进程未重启，<code>/api/agents/all</code> 路由未注册（HTTP 404）</li>
                      <li>dev 模式 workdir 指向错误目录，读不到 agents/*.yaml</li>
                      <li>agents 目录确实为空</li>
                    </ul>
                  </div>
                </div>
              }
              action={
                <button
                  onClick={checkDebug}
                  className="text-xs px-2 py-1 border border-gray-300 rounded bg-white hover:bg-gray-50"
                >
                  检测 API 响应
                </button>
              }
            />
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
              gap: 12,
              padding: 4,
            }}
          >
            {grouped.map((group) => {
              const onlineInGroup = group.items.filter((a) => a.connected).length;
              return (
                <div key={group.sourceFile} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {/* group header — 粘性置顶 */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 10px',
                      background: '#f9fafb',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                      position: 'sticky',
                      top: 0,
                      zIndex: 1,
                    }}
                  >
                    <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#374151', fontWeight: 500 }}>
                      {group.sourceFile}
                    </span>
                    <Tag style={{ marginLeft: 4 }}>
                      {group.items.length} 个 agent
                    </Tag>
                    {onlineInGroup > 0 && (
                      <Tag color="green">
                        {onlineInGroup} 在线
                      </Tag>
                    )}
                    {onlineInGroup < group.items.length && (
                      <Tag color="default">
                        {group.items.length - onlineInGroup} 离线
                      </Tag>
                    )}
                  </div>
                  {/* 卡片网格 */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))',
                      gap: 12,
                      padding: 4,
                    }}
                  >
                    {group.items.map((a) => {
                      const det = detected[a.agent_id];
                      return (
                        <ServerCard
                          key={a.agent_id}
                          agent={a}
                          detectedSystem={det?.system}
                          detectedArch={det?.arch}
                          onShowDetail={handleShowDetail}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Host 详情 modal */}
      <HostInfoModal open={!!detailAgent} agent={detailAgent} onClose={handleCloseDetail} />
    </div>
  );
}

/** 卡片骨架屏：shimmer 动画 */
function ServerCardSkeleton() {
  return (
    <div
      style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        padding: 16,
        height: 158,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <style>{`
        @keyframes serverCardShimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .server-card-skeleton-line {
          background: linear-gradient(90deg, #f3f4f6 0%, #e5e7eb 50%, #f3f4f6 100%);
          background-size: 200% 100%;
          animation: serverCardShimmer 1.4s linear infinite;
          border-radius: 4px;
        }
      `}</style>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <div className="server-card-skeleton-line" style={{ width: 44, height: 44, borderRadius: 8 }} />
        <div style={{ flex: 1 }}>
          <div className="server-card-skeleton-line" style={{ width: '60%', height: 14, marginBottom: 6 }} />
          <div className="server-card-skeleton-line" style={{ width: '40%', height: 11 }} />
        </div>
        <div className="server-card-skeleton-line" style={{ width: 32, height: 16, borderRadius: 4 }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px' }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="server-card-skeleton-line" style={{ width: '90%', height: 12 }} />
        ))}
      </div>
    </div>
  );
}
