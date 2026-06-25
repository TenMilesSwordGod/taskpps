import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-layout';
import {
  DashboardOutlined,
  PartitionOutlined,
  HistoryOutlined,
  CloudServerOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';

function CurrentTime() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const pad = (n: number) => String(n).padStart(2, '0');
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

  return (
    <div style={{ fontFamily: 'monospace', lineHeight: 1.2, fontSize: 13 }}>
      <div>{date}</div>
      <div style={{ fontWeight: 600 }}>{time}</div>
    </div>
  );
}

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
  {
    path: '/plugins',
    name: '插件',
    icon: <ApiOutlined />,
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
      layout="mix"
      collapsed={collapsed}
      onCollapse={setCollapsed}
      location={{ pathname: location.pathname }}
      route={{ routes: menuRoutes }}
      menuItemRender={(item, dom) => (
        <div onClick={() => item.path && navigate(item.path)}>{dom}</div>
      )}
      actionsRender={() => [<CurrentTime key="clock" />]}
      contentStyle={{ padding: 0, height: '100%', overflow: 'hidden' }}
      style={{ height: '100vh' }}
    >
      {children}
    </ProLayout>
  );
}
