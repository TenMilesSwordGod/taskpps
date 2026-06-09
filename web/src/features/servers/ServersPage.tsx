import { useState, useMemo } from 'react';
import { Input, Empty, Tag, Spin, Badge, Tooltip, Alert } from 'antd';
import { Search, Server, RefreshCw, AlertCircle, Radar } from 'lucide-react';
import { useAgentsWithConfig } from '@/api/agents';
import ServerCard from './ServerCard';
import apiClient from '@/api/client';
import type { AgentCheckResult } from '@/types';

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
          <div className="flex items-center justify-center h-full">
            <Spin size="large" />
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
            {filtered.map((a) => {
              const det = detected[a.agent_id];
              return (
                <ServerCard
                  key={a.agent_id}
                  agent={a}
                  detectedSystem={det?.system}
                  detectedArch={det?.arch}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
