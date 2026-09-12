import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ProLayout } from '@ant-design/pro-layout';
import { LogOut, ChevronDown } from 'lucide-react';
import { Avatar, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import type { ReactNode } from 'react';
import TaskPpsLogo from '@/components/TaskPpsLogo';
import { DashboardIcon, PipelineIcon, RunHistoryIcon, ServerIcon, PluginIcon } from '@/components/icons';
import { useMe, useLogout } from '@/api/auth';
import type { AuthUser } from '@/api/auth';

function CurrentTime() {
  const [now, setNow] = useState(() => new Date());

  // v2 (2026-07): 每秒刷新改为每分钟刷新（减少视觉噪音），去掉秒显示
  useEffect(() => {
    const secToNextMinute = (60 - new Date().getSeconds()) * 1000;
    const timeout = setTimeout(() => {
      setNow(new Date());
      const timer = setInterval(() => setNow(new Date()), 60000);
      timeoutRef = timer;
    }, secToNextMinute);
    let timeoutRef: ReturnType<typeof setInterval>;
    return () => {
      clearTimeout(timeout);
      clearInterval(timeoutRef);
    };
  }, []);

  const pad = (n: number) => String(n).padStart(2, '0');
  const time = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

  return (
    <div style={{ fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace', lineHeight: 1.3, fontSize: 12 }}>
      <div style={{ color: '#94A3B8' }}>{date}</div>
      <div style={{ fontWeight: 500, color: '#0F172A' }}>{time}</div>
    </div>
  );
}

/** 菜单项定义 */
// v1 (2026-07, issue #204): 首项 path 由 '/' 改为 '/dashboard'，与路由迁移对齐（spec 4.2）
// v2 (2026-09): 导航图标由 AntD 默认图标替换为品牌图标库（工程蓝图风格），
//   流水线/服务器/插件使用项目领域语义图形，避免与通用图标混淆。
const menuRoutes = [
  {
    path: '/dashboard',
    name: '仪表盘',
    icon: <DashboardIcon />,
  },
  {
    path: '/pipelines',
    name: '流水线',
    icon: <PipelineIcon />,
  },
  {
    path: '/runs',
    name: '运行历史',
    icon: <RunHistoryIcon />,
  },
  {
    path: '/servers',
    name: '服务器',
    icon: <ServerIcon />,
  },
  {
    path: '/plugins',
    name: '插件',
    icon: <PluginIcon />,
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
  // 空值兜底（设计决策）：后端 /me 实际返回可能缺失 nickname（undefined/null）或旧数据
  // 缺 username。直接调用 String.prototype.charAt 会抛 TypeError，导致 UserMenuFooter
  // 渲染失败并向上冒泡使整页白屏。此处对所有展示字段做空值兜底，仅用于防御性渲染，
  // 不作任何业务假数据填充（no-fallback）。
  const nickname = user.nickname ?? '';
  // 头像首字符：优先 nickname 首字母，缺失时用 username 首字母，再缺失用占位 '?'
  const avatarChar = (nickname || user.username || '?').charAt(0).toUpperCase();
  // 信息块昵称：nickname 缺失时显示默认文本"未命名"，避免空白且语义明确
  const displayName = nickname || '未命名';

  // Dropdown menu items：信息块（disabled 不可点） + 分隔线 + 退出登录
  const items: MenuProps['items'] = [
    {
      key: 'info',
      disabled: true,
      label: (
        <div style={{ padding: '4px 0' }}>
          <div style={{ fontWeight: 500, color: '#121620' }}>{displayName}</div>
          <div
            style={{
              color: '#7C7F88',
              fontSize: 12,
              fontFamily: 'JetBrains Mono, SF Mono, Monaco, monospace',
            }}
          >
            {user.username ?? ''} · {user.role ?? ''}
          </div>
        </div>
      ),
    },
    { type: 'divider' },
    {
      key: 'logout',
      label: '退出登录',
      icon: <LogOut size={16} />,
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
          {avatarChar}
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
                {displayName}
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
                {user.username ?? ''}
              </div>
            </div>
            <ChevronDown size={12} style={{ color: '#7C7F88' }} />
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

  // 顶部 actions：始终显示时钟（已移除昵称展示）
  const actions: ReactNode[] = [<CurrentTime key="clock" />];

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
