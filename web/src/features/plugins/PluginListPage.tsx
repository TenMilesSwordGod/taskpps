import { useState, useMemo } from 'react';
import { Table, Tag, Button, Switch, Input, Empty, Space, Tooltip, Segmented } from 'antd';
import {
  PlugZap,
  Search,
  RefreshCw,
  Eye,
  type LucideIcon,
} from 'lucide-react';
import { usePlugins } from '@/api/plugins';
import PluginDetailModal from './PluginDetailModal';
import apiClient from '@/api/client';
import type { PluginResponse, PluginType } from '@/types';
import { useQueryClient } from '@tanstack/react-query';

/** 插件类型对应的图标和颜色 */
const TYPE_META: Record<PluginType, { icon: LucideIcon; color: string; label: string }> = {
  TriggerPlugin: { icon: PlugZap, color: 'blue', label: '触发器' },
  NotifierPlugin: { icon: PlugZap, color: 'green', label: '通知器' },
  ExecutorPlugin: { icon: PlugZap, color: 'orange', label: '执行器' },
};

const TYPE_FILTER_OPTIONS: { label: string; value: string }[] = [
  { label: '全部', value: '' },
  ...Object.entries(TYPE_META).map(([key, meta]) => ({
    label: meta.label,
    value: key,
  })),
];

export default function PluginListPage() {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [detailPlugin, setDetailPlugin] = useState<PluginResponse | null>(null);

  const { data: plugins, isLoading, isFetching, refetch } = usePlugins(typeFilter || undefined);
  const queryClient = useQueryClient();

  const handleToggle = async (plugin: PluginResponse) => {
    try {
      await apiClient.patch(`/api/plugins/${plugin.name}/toggle`);
      queryClient.invalidateQueries({ queryKey: ['plugins'] });
    } catch (err) {
      console.error('Toggle plugin failed:', err);
    }
  };

  const filtered = useMemo(() => {
    const list = plugins ?? [];
    if (!search) return list;
    const s = search.toLowerCase();
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(s) ||
        p.type.toLowerCase().includes(s) ||
        p.version.toLowerCase().includes(s),
    );
  }, [plugins, search]);

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 280,
      render: (name: string) => (
        <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 12, color: '#121620' }}>{name}</span>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 140,
      render: (type: PluginType) => {
        const meta = TYPE_META[type];
        return meta ? (
          <Tag color={meta.color} style={{ borderRadius: 3 }}>{meta.label}</Tag>
        ) : (
          <Tag style={{ borderRadius: 3 }}>{type}</Tag>
        );
      },
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      width: 100,
      render: (v: string) => <Tag style={{ borderRadius: 3 }}>{v}</Tag>,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (_enabled: boolean, record: PluginResponse) => (
        <Switch
          size="small"
          checked={record.enabled}
          onChange={() => handleToggle(record)}
        />
      ),
    },
    {
      title: '运行状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string | undefined) => {
        if (!status) return <Tag style={{ borderRadius: 3 }}>unknown</Tag>;
        const colorMap: Record<string, string> = {
          loaded: 'green',
          crashed: 'red',
          db_only: 'yellow',
        };
        return <Tag color={colorMap[status] ?? 'default'} style={{ borderRadius: 3 }}>{status}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, record: PluginResponse) => (
        <Space>
          <Tooltip title="查看详情">
            <Button
              type="text"
              size="small"
              icon={<Eye size={14} />}
              onClick={() => setDetailPlugin(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex flex-col h-full p-6 gap-3" style={{ background: '#F6F6F8' }}>
      <div className="shrink-0 px-5 py-3 flex items-center justify-between gap-3 flex-wrap" style={{ background: '#FFFFFF', borderRadius: 8, border: '1px solid #E3E4E8', boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px' }}>
        <div className="flex items-center gap-2">
          <PlugZap size={18} color="#7C7F88" />
          <span className="text-base font-semibold" style={{ color: '#121620' }}>插件管理</span>
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs" style={{ background: '#F6F6F8', color: '#7C7F88' }}>
            共 {plugins?.length ?? 0} 个
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Segmented
            size="small"
            options={TYPE_FILTER_OPTIONS}
            value={typeFilter}
            onChange={(v) => setTypeFilter(v as string)}
          />
          <Input
            allowClear
            prefix={<Search size={14} color="#7C7F88" />}
            placeholder="搜索名称 / 类型 / 版本"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 240 }}
          />
          <Tooltip title="刷新">
            <Button
              size="small"
              icon={<RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />}
              onClick={() => refetch()}
              disabled={isFetching}
            >
              刷新
            </Button>
          </Tooltip>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading ? (
          <div className="p-4">
            <Table
              columns={columns}
              dataSource={[]}
              loading
              rowKey="id"
              pagination={false}
            />
          </div>
        ) : filtered.length === 0 ? (
          <Empty
            description={
              <span style={{ color: '#7C7F88' }}>
                {plugins?.length === 0 ? '暂无已注册插件' : '无匹配的插件'}
              </span>
            }
            className="mt-16"
          />
        ) : (
          <Table
            columns={columns}
            dataSource={filtered}
            rowKey="id"
            pagination={false}
            size="middle"
            className="overflow-hidden"
            style={{ background: '#FFFFFF', borderRadius: 8, border: '1px solid #E3E4E8', boxShadow: 'rgba(1, 24, 33, 0.05) 0px 0px 0px 1px' }}
          />
        )}
      </div>

      <PluginDetailModal
        plugin={detailPlugin}
        onClose={() => setDetailPlugin(null)}
      />
    </div>
  );
}
