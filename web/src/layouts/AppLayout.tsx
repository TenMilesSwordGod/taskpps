import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-layout';
import {
  DashboardOutlined,
  PartitionOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';

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
];

interface AppLayoutProps {
  children: ReactNode;
}

/** 应用布局 */
export default function AppLayout({ children }: AppLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

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
      contentStyle={{ padding: 0, height: '100%', overflow: 'hidden' }}
      style={{ height: '100vh' }}
    >
      {children}
    </ProLayout>
  );
}
