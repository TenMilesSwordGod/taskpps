import { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { Input, Empty, Tag, Tooltip, Alert, Button, Segmented, App } from 'antd';
import {
  Search, Server, RefreshCw, AlertCircle, Radar,
  ChevronRight, FolderOpen, Clock, Plus, KeyRound,
} from 'lucide-react';
import { useAgentsWithConfig, useDeleteAgent } from '@/api/agents';
import { useProjects } from '@/api/projects';
import { useIsAdmin } from '@/hooks/useIsAdmin';
import ServerCard from './ServerCard';
import HostInfoModal from './HostInfoModal';
import ReplModal from './ReplModal';
import AgentFormModal from './AgentFormModal';
import CredentialsModal from './CredentialsModal';
import apiClient from '@/api/client';
import { RelativeTime } from '@/components/RelativeTime';
import type { AgentCheckResult, AgentWithConfig, ProjectResponse } from '@/types';

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
  const { data: agents, isLoading, refetch, isFetching, error, dataUpdatedAt } = useAgentsWithConfig();
  const { message } = App.useApp();
  // 仅管理员可见写入口（后端对所有写接口同样做 admin 校验，前端隐藏只是减少误操作）
  const isAdmin = useIsAdmin();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  // 折叠的项目 ID 集合（默认全部展开，点击折叠后加入集合）
  const [collapsedProjects, setCollapsedProjects] = useState<Set<string>>(new Set());
  // 探测结果（agent_id → { system, arch }），用于按需覆盖 yaml 兜底
  const [detected, setDetected] = useState<Record<string, { system: string; arch: string }>>({});
  const [probing, setProbing] = useState(false);
  // 服务器新增/编辑弹窗状态（editingAgent 为 null 表示新增）
  const [agentFormOpen, setAgentFormOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentWithConfig | null>(null);
  // 凭据管理弹窗；从空态/工具栏打开
  const [credentialsOpen, setCredentialsOpen] = useState(false);
  const [credentialsProjectId, setCredentialsProjectId] = useState<string | undefined>(undefined);
  const deleteAgent = useDeleteAgent();

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

  // 空配置引导：仅当接口正常且无任何 agent 时，拉取项目列表以展示确切的 agents/ 目录。
  // 设计决策（为什么这么写）：区分"接口正常但确实没配"与"请求失败"两种空态，
  // 避免页面正常返回空数组时展示猜测性故障原因；有数据时不发这次请求。
  // 管理员还需要项目列表来填充"新增服务器"弹窗，因此 admin 始终加载。
  const showConfigGuide = !isLoading && !error && totalCount === 0;
  const { data: projects, isLoading: projectsLoading, isError: projectsError } = useProjects(showConfigGuide || isAdmin);

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

  // REPL modal 状态
  const [replAgent, setReplAgent] = useState<AgentWithConfig | null>(null);
  const handleShowRepl = useCallback((agent: AgentWithConfig) => {
    setReplAgent(agent);
  }, []);
  const handleCloseRepl = useCallback(() => setReplAgent(null), []);

  // 新增服务器（可带入默认项目，例如从空态引导直接进入）
  const [defaultProjectId, setDefaultProjectId] = useState<string | undefined>(undefined);
  const handleCreateAgent = useCallback((presetProjectId?: string) => {
    setEditingAgent(null);
    setDefaultProjectId(presetProjectId);
    setAgentFormOpen(true);
  }, []);
  const handleEditAgent = useCallback((agent: AgentWithConfig) => {
    setEditingAgent(agent);
    setDefaultProjectId(undefined);
    setAgentFormOpen(true);
  }, []);
  const handleDeleteAgent = useCallback(
    (agent: AgentWithConfig) => {
      if (!agent.project_id) return;
      deleteAgent.mutate(
        { projectId: agent.project_id, agentId: agent.agent_id },
        {
          onSuccess: () => message.success(`服务器 ${agent.agent_id} 已删除`),
          // 被流水线引用时后端返回 409，直接把原因展示出来（含引用文件清单）
          onError: (e: unknown) => message.error(e instanceof Error ? e.message : '删除服务器失败'),
        },
      );
    },
    [deleteAgent, message],
  );
  const handleManageCredentials = useCallback((projectId?: string) => {
    setCredentialsProjectId(projectId);
    setCredentialsOpen(true);
  }, []);

  return (
    <div className="flex flex-col h-full p-6 gap-3" style={{ background: '#F6F6F8' }}>
      <style>{`
        @keyframes pageSyncPulse {
          0% { transform: scale(1); opacity: 0.35; }
          70% { transform: scale(2.2); opacity: 0; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @media (prefers-reduced-motion: reduce) {
          @keyframes pageSyncPulse { 0%,100% { opacity: 0; } }
        }
      `}</style>
      {/* 顶部工具栏 */}
      <div className="shrink-0 px-5 py-3 flex items-center justify-between gap-3 flex-wrap" style={{ background: '#FFFFFF', borderRadius: 8, border: '1px solid #E3E4E8', boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px' }}>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Server size={18} color="#7C7F88" />
            <span className="text-base font-semibold" style={{ color: '#121620' }}>服务器列表</span>
          </div>
          {/* 统计胶囊 */}
          <div className="flex items-center gap-1.5 text-xs">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full" style={{ background: '#F6F6F8', color: '#7C7F88' }}>
              总计 {totalCount}
            </span>
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full" style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', flexShrink: 0 }} />
              在线 {onlineCount}
            </span>
            {offlineCount > 0 && (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full" style={{ background: '#F6F6F8', color: '#7C7F88' }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#C9CBD3', flexShrink: 0 }} />
                离线 {offlineCount}
              </span>
            )}
            {/* 上次更新时间 + 全局呼吸灯：代表正在后台获取信息中 */}
            {dataUpdatedAt > 0 && (
              <span
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full"
                style={{ background: '#F6F6F8', color: '#7C7F88' }}
                title={new Date(dataUpdatedAt).toLocaleString('zh-CN')}
              >
                <span
                  style={{
                    width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                    // 仅在首个后端数据加载时显示呼吸灯；后台刷新时保持静态点，避免每5s闪烁
                    background: isLoading ? '#F59E0B' : '#C9CBD3',
                    boxShadow: isLoading ? '0 0 6px rgba(245, 158, 11, 0.5)' : 'none',
                    animation: isLoading ? 'pageSyncPulse 1.8s ease-out infinite' : 'none',
                  }}
                />
                <Clock size={11} style={{ flexShrink: 0 }} />
                <RelativeTime tsMs={dataUpdatedAt} prefix="更新于" />
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
            prefix={<Search size={14} color="#7C7F88" />}
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
          {isAdmin && (
            <Tooltip title="管理服务器登录凭据（密码加密存储，保存后不可查看明文）">
              <Button
                size="small"
                icon={<KeyRound size={14} />}
                onClick={() => handleManageCredentials(undefined)}
              >
                凭据管理
              </Button>
            </Tooltip>
          )}
          {isAdmin && (
            <Tooltip
              title={
                (projects ?? []).length === 0
                  ? '请先注册项目目录，服务器配置需要写入项目的 agents/ 目录'
                  : ''
              }
            >
              {/* 无项目时禁用并提供原因，避免打开空表单无法提交的挫败感 */}
              <Button
                size="small"
                type="primary"
                icon={<Plus size={14} />}
                disabled={(projects ?? []).length === 0}
                onClick={() => handleCreateAgent()}
              >
                新增服务器
              </Button>
            </Tooltip>
          )}
        </div>
      </div>

      {/* 卡片网格 */}
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="p-1 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))' }}>
            {[1, 2, 3, 4].map((i) => <ServerCardSkeleton key={i} />)}
          </div>
        ) : error && totalCount === 0 ? (
          /* 请求失败：展示真实错误与重试入口，不做原因猜测 */
          <div className="p-4">
            <Alert
              type="error"
              showIcon
              icon={<AlertCircle size={16} />}
              message="无法获取服务器列表"
              description={
                <div className="space-y-1 text-xs">
                  <div>API: <code>GET /api/agents/all</code></div>
                  <div>错误：{error instanceof Error ? error.message : String(error)}</div>
                </div>
              }
              action={<Button size="small" onClick={() => refetch()}>重试</Button>}
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-4">
            {totalCount === 0 ? (
              <EmptyAgentsGuide
                projects={projects}
                projectsLoading={projectsLoading}
                projectsError={projectsError}
                refreshing={isFetching}
                onRefresh={() => refetch()}
                isAdmin={isAdmin}
                onAddServer={() => handleCreateAgent(projects?.[0]?.id)}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={<span style={{ color: '#7C7F88' }}>无匹配的服务器</span>}
              />
            )}
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
                    className="group sticky top-0 z-10 flex items-center gap-2 px-4 py-2.5 transition-colors cursor-pointer"
                    style={{
                      background: '#FFFFFF',
                      border: '1px solid #E3E4E8',
                      borderRadius: 8,
                      transitionTimingFunction: 'cubic-bezier(0.76, 0, 0.24, 1)',
                      transitionDuration: '220ms',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = '#F6F6F8'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = '#FFFFFF'; }}
                  >
                    <ChevronRight
                      size={14}
                      style={{ color: '#7C7F88', transition: 'transform 200ms cubic-bezier(0.76, 0, 0.24, 1)' }}
                      className={isCollapsed ? '' : 'rotate-90'}
                    />
                    <FolderOpen size={14} color={isDefault ? '#7C7F88' : '#3D5BFF'} />
                    <span className="text-sm font-semibold" style={{ color: isDefault ? '#7C7F88' : '#121620' }}>
                      {group.projectName}
                    </span>
                    <Tag className="!m-0 !text-xs" color="default" style={{ borderRadius: 3 }}>
                      {group.items.length} 台
                    </Tag>
                    {onlineInGroup > 0 && (
                      <Tag className="!m-0 !text-xs" color="success" style={{ borderRadius: 3 }}>
                        {onlineInGroup} 在线
                      </Tag>
                    )}
                    {offlineInGroup > 0 && (
                      <Tag className="!m-0 !text-xs" color="default" style={{ borderRadius: 3 }}>
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
                            onShowRepl={handleShowRepl}
                            isAdmin={isAdmin}
                            onEdit={handleEditAgent}
                            onDelete={handleDeleteAgent}
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

      {/* Web REPL modal */}
      <ReplModal open={!!replAgent} agent={replAgent} onClose={handleCloseRepl} />

      {/* 新增/编辑服务器（仅管理员入口可达，后端同样校验） */}
      <AgentFormModal
        open={agentFormOpen}
        agent={editingAgent}
        projects={projects ?? []}
        defaultProjectId={defaultProjectId}
        onClose={() => setAgentFormOpen(false)}
      />

      {/* 凭据管理（仅管理员入口可达） */}
      <CredentialsModal
        open={credentialsOpen}
        initialProjectId={credentialsProjectId}
        onClose={() => setCredentialsOpen(false)}
      />
    </div>
  );
}

/**
 * 无 agent 配置时的引导面板。
 *
 * 设计决策（为什么这么写）：
 * - 仅在后端成功返回空数组时展示，用确定性信息说明"配置放哪里"，
 *   取代原先罗列"可能原因"（404/目录错误等）的诊断面板——那属于无依据猜测。
 * - 已注册项目时直接列出各项目 workdir 下的 agents/ 目录，运维可直接照路径创建；
 *   未注册项目时说明后端会回退读取默认工作目录的 agents/ 目录，不编造具体路径。
 * - 项目列表自身获取失败时明确提示失败，不谎称"未注册任何项目"。
 */
function EmptyAgentsGuide({
  projects,
  projectsLoading,
  projectsError,
  refreshing,
  onRefresh,
  isAdmin,
  onAddServer,
}: {
  projects?: ProjectResponse[];
  projectsLoading: boolean;
  projectsError: boolean;
  refreshing: boolean;
  onRefresh: () => void;
  isAdmin: boolean;
  onAddServer: () => void;
}) {
  const projectList = projects ?? [];
  return (
    <div
      style={{
        maxWidth: 560,
        margin: '48px auto 0',
        padding: '24px 28px',
        background: '#FFFFFF',
        border: '1px solid #E3E4E8',
        borderRadius: 8,
        textAlign: 'center',
        boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px',
      }}
    >
      <Server size={28} color="#C9CBD3" style={{ marginBottom: 12 }} />
      <div className="text-sm font-semibold" style={{ color: '#121620', marginBottom: 8 }}>
        暂无 agent 配置
      </div>
      {projectsLoading ? (
        <div className="text-xs" style={{ color: '#7C7F88' }}>正在检查已注册项目的 agent 配置…</div>
      ) : projectsError ? (
        <div className="text-xs" style={{ color: '#7C7F88' }}>
          后端会从项目工作目录的 <code>agents/*.yaml</code> 读取配置；
          项目列表获取失败，请确认配置文件路径后点击刷新。
        </div>
      ) : projectList.length > 0 ? (
        <div className="text-xs" style={{ color: '#7C7F88', textAlign: 'left' }}>
          <div style={{ marginBottom: 6 }}>
            后端会从各项目的 <code>agents/*.yaml</code> 读取配置，以下项目下暂未找到 agent 配置：
          </div>
          <ul className="list-disc pl-5 space-y-1">
            {projectList.map((p) => (
              <li key={p.id}>
                <span style={{ color: '#121620' }}>{p.name || p.id}</span>
                <span style={{ color: '#7C7F88' }}>：</span>
                <code>{p.workdir}/agents</code>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="text-xs" style={{ color: '#7C7F88' }}>
          后端会从项目工作目录的 <code>agents/*.yaml</code> 读取配置。当前未注册项目，
          请先在服务端默认工作目录的 <code>agents/</code> 目录下创建配置文件。
        </div>
      )}
      {isAdmin && (
        <Button
          type="primary"
          size="small"
          icon={<Plus size={14} />}
          onClick={onAddServer}
          disabled={projectsLoading || (projects ?? []).length === 0}
          style={{ marginTop: 16, marginRight: 8 }}
        >
          新增服务器
        </Button>
      )}
      <Button
        size="small"
        icon={<RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />}
        onClick={onRefresh}
        disabled={refreshing}
        style={{ marginTop: 16 }}
      >
        刷新
      </Button>
    </div>
  );
}

/** 卡片骨架屏：shimmer 动画 */
function ServerCardSkeleton() {
  return (
    <div
      style={{
        background: '#FFFFFF',
        border: '1px solid #E3E4E8',
        borderRadius: 8,
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
          background: linear-gradient(90deg, #F6F6F8 0%, #E3E4E8 50%, #F6F6F8 100%);
          background-size: 200% 100%;
          animation: serverCardShimmer 1.4s linear infinite;
          border-radius: 3px;
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
