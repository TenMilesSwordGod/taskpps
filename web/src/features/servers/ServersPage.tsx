import { useState, useMemo } from 'react';
import { Input, Empty, Tag, Spin, Badge, Tooltip } from 'antd';
import { Search, Server, RefreshCw } from 'lucide-react';
import { useAgents } from '@/api/agents';
import ServerCard from './ServerCard';

/** Servers 列表页 */
export default function ServersPage() {
  const { data: agents, isLoading, refetch, isFetching } = useAgents();
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    const list = agents ?? [];
    if (!search) return list;
    const s = search.toLowerCase();
    return list.filter(
      (a) =>
        a.agent_id.toLowerCase().includes(s) ||
        a.hostname.toLowerCase().includes(s) ||
        a.ip.toLowerCase().includes(s) ||
        a.system.toLowerCase().includes(s) ||
        a.arch.toLowerCase().includes(s),
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
            placeholder="搜索 ID / 主机名 / IP / 系统 / 架构"
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
        </div>
      </div>

      {/* 卡片网格 */}
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Spin size="large" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span style={{ color: '#6b7280' }}>
                  {totalCount === 0 ? '暂无 agent 连接' : '无匹配的服务器'}
                </span>
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
            {filtered.map((a) => (
              <ServerCard key={a.agent_id} agent={a} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
