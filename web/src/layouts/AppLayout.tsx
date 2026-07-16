import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-layout';
import {
  DashboardOutlined,
  PartitionOutlined,
  HistoryOutlined,
  CloudServerOutlined,
  ApiOutlined,
  LogoutOutlined,
  DownOutlined,
} from '@ant-design/icons';
import { Avatar, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import type { ReactNode } from 'react';
import TaskPpsLogo from '@/components/TaskPpsLogo';
import { useMe, useLogout } from '@/api/auth';
import type { AuthUser } from '@/api/auth';

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
    <div style={{ fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace', lineHeight: 1.3, fontSize: 12 }}>
      <div style={{ color: '#7C7F88' }}>{date}</div>
      <div style={{ fontWeight: 500, color: '#121620' }}>{time}</div>
    </div>
  );
}

/** 菜单项定义 */
// v1 (2026-07, issue #204): 首项 path 由 '/' 改为 '/dashboard'，与路由迁移对齐（spec 4.2）
const menuRoutes = [
  {
    path: '/dashboard',
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

/**
 * 侧边栏底部用户头像区（签名元素，spec 4.3）。
 *
 * 设计决策（为什么这么写）：
 * - 通过 ProLayout menuFooterRender 渲染在 sider 最底部，固定不被滚动（spec 4.3.1）。
 * - 展开态：头像 + 昵称 + 用户名 + 下拉箭头；折叠态：仅头像（spec 4.3.2/4.3.3）。
 * - 点击触发 Dropdown（menu 模式），含用户信息块 + 分隔线 + 退出登录（spec 4.3.4）。
 * - 头像 src 加载失败时降级为昵称首字符（AntD Avatar 内置 onError → 显示 children）。
 * - 角色用英文小写 + JetBrains Mono，与项目技术风格一致（spec 4.3.4）。
 */
function UserMenuFooter({
  user,
  collapsed,
  onLogout,
}: {
  user: AuthUser;
  collapsed: boolean;
  onLogout: () => void;
}) {
  // Dropdown menu items：信息块（disabled 不可点） + 分隔线 + 退出登录
  const items: MenuProps['items'] = [
    {
      key: 'info',
      disabled: true,
      label: (
        <div style={{ padding: '4px 0' }}>
          <div style={{ fontWeight: 500, color: '#121620' }}>{user.nickname}</div>
          <div
            style={{
              color: '#7C7F88',
              fontSize: 12,
              fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace',
            }}
          >
            {user.username} · {user.role}
          </div>
        </div>
      ),
    },
    { type: 'divider' },
    {
      key: 'logout',
      label: '退出登录',
      icon: <LogoutOutlined />,
      danger: true,
    },
  ];

  const onClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') onLogout();
  };

  return (
    <Dropdown menu={{ items, onClick }} trigger={['click']} placement="topLeft">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: collapsed ? '8px 0' : '10px 12px',
          justifyContent: collapsed ? 'center' : 'flex-start',
          borderTop: '1px solid #E3E4E8',
          cursor: 'pointer',
        }}
      >
        <Avatar
          src={user.avatar}
          size={36}
          style={{ backgroundColor: '#3D5BFF', color: '#FFFFFF', flexShrink: 0 }}
        >
          {user.nickname.charAt(0).toUpperCase()}
        </Avatar>
        {!collapsed && (
          <>
            <div style={{ flex: 1, minWidth: 0, lineHeight: 1.3 }}>
              <div
                style={{
                  color: '#121620',
                  fontWeight: 500,
                  fontSize: 13,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {user.nickname}
              </div>
              <div
                style={{
                  color: '#7C7F88',
                  fontSize: 12,
                  fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {user.username}
              </div>
            </div>
            <DownOutlined style={{ color: '#7C7F88', fontSize: 10 }} />
          </>
        )}
      </div>
    </Dropdown>
  );
}

interface AppLayoutProps {
  children: ReactNode;
}

/**
 * 应用布局（issue #204 增强侧边栏头像 + 顶部昵称）。
 *
 * v1 (2026-07, issue #204):
 * - 接入 useMe：已登录时 sider 底部渲染用户头像区，header 右侧渲染昵称。
 * - 未登录（guest 访问 /dashboard）时不渲染头像与昵称（spec 4.3.5）。
 * - 退出登录：调后端 no-op → onSettled 清 token + queryClient.clear() → 跳 /login。
 */
export default function AppLayout({ children }: AppLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { data: user } = useMe();
  const logoutMutation = useLogout();

  /** 退出登录：try/finally 确保即使后端调用失败也跳转 /login */
  const handleLogout = async () => {
    try {
      await logoutMutation.mutateAsync();
    } finally {
      // useLogout onSettled 已清 token + queryClient.clear()，此处只负责跳转
      navigate('/login', { replace: true });
    }
  };

  // 顶部 actions：已登录显示昵称（spec 4.3.5），始终显示时钟
  const actions: ReactNode[] = [];
  if (user) {
    actions.push(
      <span
        key="nickname"
        style={{ color: '#121620', fontSize: 13, fontWeight: 500, marginRight: 12 }}
      >
        {user.nickname}
      </span>,
    );
  }
  actions.push(<CurrentTime key="clock" />);

  return (
    <ProLayout
      title="TaskPPS"
      logo={<TaskPpsLogo size={28} />}
      layout="mix"
      collapsed={collapsed}
      onCollapse={setCollapsed}
      location={{ pathname: location.pathname }}
      route={{ routes: menuRoutes }}
      menuItemRender={(item, dom) => (
        <div onClick={() => item.path && navigate(item.path)}>{dom}</div>
      )}
      actionsRender={() => actions}
      menuFooterRender={() =>
        user ? (
          <UserMenuFooter user={user} collapsed={collapsed} onLogout={handleLogout} />
        ) : null
      }
      contentStyle={{ padding: 0, height: '100%', overflow: 'hidden' }}
      style={{ height: '100vh' }}
      siderWidth={220}
    >
      {children}
    </ProLayout>
  );
}
