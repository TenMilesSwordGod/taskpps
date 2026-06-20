import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { Input, Empty, Tag, Tooltip, Alert, Button, Segmented } from 'antd';
import {
  Search, Server, RefreshCw, AlertCircle, Radar,
  ChevronRight, FolderOpen, CircleDot,
} from 'lucide-react';
import { useAgentsWithConfig } from '@/api/agents';
import ServerCard from './ServerCard';
import HostInfoModal from './HostInfoModal';
import apiClient from '@/api/client';
import type { AgentCheckResult, AgentWithConfig } from '@/types';

type StatusFilter = 'all' | 'online' | 'offline';

/** 项目分组 */
interface ProjectGroup {
  projectId: string;
  projectName: string;
  items: AgentWithConfig[];
}

/** 默认项目 ID（project_id 为空时归入此组） */
const DEFAULT_PROJECT_ID = '__default__';

/** 状态过滤选项 */
const STATUS_OPTIONS: { label: React.ReactNode; value: StatusFilter }[] = [
  { label: '全部', value: 'all' },
  { label: '在线', value: 'online' },
  { label: '离线', value: 'offline' },
];

/** Servers 列表页 */
export default function ServersPage() {
  const { data: agents, isLoading, refetch, isFetching, error } = useAgentsWithConfig();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  // 折叠的项目 ID 集合（默认全部展开，点击折叠后加入集合）
  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set());
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

  // 自动探测：首次拿到 agents 后异步触发，填充 system/arch 真实值
  // trackedIds 记录已触发的 agent 集合，避免重复探测同一批
  const trackedIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!agents || agents.length === 0) return;
    // 找出需要探测且未触发过的 agent
    const needsProbe = agents.filter((a) => (!a.system || !a.arch) && !trackedIdsRef.current.has(a.agent_id));
    if (needsProbe.length === 0) return;
    // 标记已触发，避免重复
    for (const a of needsProbe) {
      trackedIdsRef.current.add(a.agent_id);
    }
    // 延迟执行，确保页面渲染完成后再发起探测请求
    const timer = setTimeout(() => { void runProbe(); }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents]);

  // 调试用：直接 raw fetch 一次，识别是"404 未重启"还是"[] 但确实没配"
  const [debugInfo, setDebugInfo] = useState<{ url: string; status: number; type: string; preview: string } | null>(null);
  const checkDebug = async () => {
    const baseURL = (import.meta.env.VITE_API_BASE_URL as string) ?? '';
    const url = `${baseURL}/api/agents/all`;
    try {
      const apiKey = (import.meta.env.VITE_API_KEY as string) ?? '';
      const headers: Record<string, string> = {};
      if (apiKey) headers['X-API-Key'] = apiKey;
      const res = await fetch(url, { headers });
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

  // 搜索 + 状态过滤
  const filtered = useMemo(() => {
    const list = agents ?? [];
    let result = list;
    if (statusFilter !== 'all') {
      result = result.filter((a) => (statusFilter === 'online' ? a.connected : !a.connected));
    }
    if (!search) return result;
    const s = search.toLowerCase();
    return result.filter(
      (a) =>
        (a.agent_id ?? '').toLowerCase().includes(s) ||
        (a.hostname ?? '').toLowerCase().includes(s) ||
        (a.name ?? '').toLowerCase().includes(s) ||
        (a.ip ?? '').toLowerCase().includes(s) ||
        (a.host ?? '').toLowerCase().includes(s) ||
        (a.system ?? '').toLowerCase().includes(s) ||
        (a.arch ?? '').toLowerCase().includes(s) ||
        (a.type ?? '').toLowerCase().includes(s) ||
        (a.project_id ?? '').toLowerCase().includes(s) ||
        (a.project_name ?? '').toLowerCase().includes(s),
    );
  }, [agents, search, statusFilter]);

  const onlineCount = (agents ?? []).filter((a) => a.connected).length;
  const totalCount = (agents ?? []).length;
  const offlineCount = totalCount - onlineCount;

  // 按项目分组（保持 yaml 内定义顺序）
  const grouped = useMemo<ProjectGroup[]>(() => {
    const groups: ProjectGroup[] = [];
    const indexMap = new Map<string, number>();
    for (const a of filtered) {
      const pid = a.project_id || DEFAULT_PROJECT_ID;
      const pname = a.project_id ? (a.project_name || a.project_id) : '默认项目';
      let idx = indexMap.get(pid);
      if (idx === undefined) {
        idx = groups.length;
        indexMap.set(pid, idx);
        groups.push({ projectId: pid, projectName: pname, items: [] });
      }
      groups[idx].items.push(a);
    }
    return groups;
  }, [filtered]);

  const toggleProject = useCallback((pid: string) => {
    setCollapsedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else next.add(pid);
      return next;
    });
  }, []);

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
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Server size={18} className="text-gray-500" />
            <span className="text-base font-semibold text-gray-800">服务器列表</span>
          </div>
          {/* 统计胶囊 */}
          <div className="flex items-center gap-2 text-xs">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
              总计 {totalCount}
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-600">
              <CircleDot size={10} className="text-emerald-500" />
              在线 {onlineCount}
            </span>
            {offlineCount > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                <CircleDot size={10} className="text-gray-400" />
                离线 {offlineCount}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Segmented
            size="small"
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={(v) => setStatusFilter(v as StatusFilter)}
          />
          <Input
            allowClear
            prefix={<Search size={14} className="text-gray-400" />}
            placeholder="搜索 ID / 名称 / IP / 系统 / 架构 / 类型"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 320 }}
          />
          <Tooltip title="手动刷新">
            <Button
              size="small"
              icon={<RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />}
              onClick={() => refetch()}
              disabled={isFetching}
            >
              刷新
            </Button>
          </Tooltip>
          <Tooltip title="主动探测所有 agent 的 system / arch（通过 SSH uname）">
            <Button
              size="small"
              icon={<Radar size={14} className={probing ? 'animate-spin' : ''} />}
              onClick={runProbe}
              disabled={probing}
            >
              {probing ? '探测中…' : '探测 system/arch'}
            </Button>
          </Tooltip>
        </div>
      </div>

      {/* 卡片网格 */}
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="p-1 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))' }}>
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
          <div className="flex flex-col gap-4 p-1">
            {grouped.map((group) => {
              const onlineInGroup = group.items.filter((a) => a.connected).length;
              const offlineInGroup = group.items.length - onlineInGroup;
              const isCollapsed = collapsedProjects.has(group.projectId);
              const isDefault = group.projectId === DEFAULT_PROJECT_ID;
              return (
                <section key={group.projectId} className="flex flex-col gap-2">
                  {/* 项目分组头 — 粘性置顶，可点击折叠 */}
                  <button
                    type="button"
                    onClick={() => toggleProject(group.projectId)}
                    className="group sticky top-0 z-10 flex items-center gap-2 px-3 py-2 bg-white/95 backdrop-blur border border-gray-200 rounded-lg shadow-sm hover:bg-gray-50 transition-colors cursor-pointer"
                  >
                    <ChevronRight
                      size={14}
                      className={`text-gray-400 transition-transform duration-200 ${isCollapsed ? '' : 'rotate-90'}`}
                    />
                    <FolderOpen size={14} className={isDefault ? 'text-gray-400' : 'text-blue-500'} />
                    <span className={`text-sm font-semibold ${isDefault ? 'text-gray-600' : 'text-gray-800'}`}>
                      {group.projectName}
                    </span>
                    <Tag className="!m-0 !text-xs" color="default">
                      {group.items.length} 台
                    </Tag>
                    {onlineInGroup > 0 && (
                      <Tag className="!m-0 !text-xs" color="success">
                        {onlineInGroup} 在线
                      </Tag>
                    )}
                    {offlineInGroup > 0 && (
                      <Tag className="!m-0 !text-xs" color="default">
                        {offlineInGroup} 离线
                      </Tag>
                    )}
                  </button>
                  {/* 卡片网格 */}
                  {!isCollapsed && (
                    <div
                      className="grid gap-3 p-1"
                      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))' }}
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
                  )}
                </section>
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
