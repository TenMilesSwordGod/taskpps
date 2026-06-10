import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-layout';
import { Select, Spin } from 'antd';
import {
  DashboardOutlined,
  PartitionOutlined,
  HistoryOutlined,
  CloudServerOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';
import { useProjects } from '@/api/projects';
import { useProjectContext } from '@/contexts/ProjectContext';

/** 菜单项定义 */
const menuRoutes = [
  {
    path: '/',
    name: '仪表盘',
    icon: <DashboardOutlined />,
  },
  {
    path: '/pipelines',
    name: '流水线',
    icon: <PartitionOutlined />,
  },
  {
    path: '/runs',
    name: '运行历史',
    icon: <HistoryOutlined />,
  },
  {
    path: '/servers',
    name: '服务器',
    icon: <CloudServerOutlined />,
  },
];

interface AppLayoutProps {
  children: ReactNode;
}

/** 应用布局 */
export default function AppLayout({ children }: AppLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const { selectedProjectId, setSelectedProjectId } = useProjectContext();

  return (
    <ProLayout
      title="TaskPPS"
      logo={false}
      layout="mix"
      collapsed={collapsed}
      onCollapse={setCollapsed}
      location={{ pathname: location.pathname }}
      route={{ routes: menuRoutes }}
      menuItemRender={(item, dom) => (
        <div onClick={() => item.path && navigate(item.path)}>{dom}</div>
      )}
      actionsRender={() => (
        <Select
          allowClear
          placeholder="选择项目"
          style={{ minWidth: 200 }}
          value={selectedProjectId}
          onChange={(val) => setSelectedProjectId(val ?? null)}
          loading={projectsLoading}
          notFoundContent={projectsLoading ? <Spin size="small" /> : '暂无项目'}
          options={(projects ?? []).map((p) => ({
            label: `${p.name || p.id} (${p.workdir})`,
            value: p.id,
          }))}
        />
      )}
      contentStyle={{ padding: 0, height: '100%', overflow: 'hidden' }}
      style={{ height: '100vh' }}
    >
      {children}
    </ProLayout>
  );
}
