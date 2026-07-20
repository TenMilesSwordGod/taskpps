import { lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router-dom';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import AppLayout from '@/layouts/AppLayout';
import { getToken } from '@/api/client';

// 路由级 code splitting：每个页面单独 chunk，首屏只下载必要的
const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'));
const PipelineListPage = lazy(() => import('@/features/pipelines/PipelineListPage'));
const PipelineDetailPage = lazy(() => import('@/features/pipelines/PipelineDetailPage'));
const RunListPage = lazy(() => import('@/features/runs/RunListPage'));
const RunDetailPage = lazy(() => import('@/features/runs/RunDetailPage'));
const ServersPage = lazy(() => import('@/features/servers/ServersPage'));
const PluginListPage = lazy(() => import('@/features/plugins/PluginListPage'));
// v1 (2026-07, issue #204): 登录页独立路由，不挂 AppLayout（spec: 全屏背景）
const LoginPage = lazy(() => import('@/pages/LoginPage'));
// v1 (2026-07, issue #206): e2e 测试专用页面 — 绕过认证，独立渲染 WorkflowEditor
const E2EWorkflowEditorPage = lazy(() => import('@/pages/E2EWorkflowEditorPage'));
// v1 (2026-07, issue #206): e2e 测试专用页面 — PipelineDetailPage 集成测试
const E2EPipelineDetailPage = lazy(() => import('@/pages/E2EPipelineDetailPage'));

/** 路由级 Suspense fallback */
function RouteFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
      <Spin size="large" />
    </div>
  );
}

const wrap = (el: ReactNode) => <Suspense fallback={<RouteFallback />}>{el}</Suspense>;

/**
 * 路由守卫（issue #204）。
 *
 * 设计决策（为什么这么写）：
 * - 仅检查 token 存在性，不在此处校验 token 有效性。
 *   token 失效由 axios 响应拦截器在 401 时统一处理（跳 /login），
 *   避免守卫内额外发 /me 请求造成首屏延迟。
 * - 用 layout route 模式（返回 <Outlet />）而非 props.children 包裹，
 *   可一次性守卫整组受保护路由，配置更聚合。
 * - redirect 携带原 pathname + search，登录后可回到原页面（spec 8.1）。
 */
function RequireAuth() {
  const location = useLocation();
  const token = getToken();
  if (!token) {
    const redirect = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?redirect=${redirect}`} replace />;
  }
  return <Outlet />;
}

/**
 * AppLayout 适配器：把 children prop 模式桥接到 layout route 的 <Outlet />。
 * 保留 AppLayout 的 children 接口不变，减少对现有组件签名的扰动。
 */
function AppLayoutWithOutlet() {
  return (
    <AppLayout>
      <Outlet />
    </AppLayout>
  );
}

/**
 * 路由定义（issue #204 重构）。
 *
 * 结构：
 * - /login 独立路由，不挂 AppLayout（spec 4.1：全屏背景居中卡片）。
 * - AppLayout 布局路由：包裹所有应用页面，提供侧边栏 + 顶栏。
 *   - / 重定向到 /dashboard（spec 4.2）。
 *   - /dashboard 公开（spec 3-3：guest 可读，路由白名单）。
 *   - RequireAuth 布局路由：包裹受保护路由（/pipelines /runs /servers /plugins，spec 8.1）。
 */
const routes: RouteObject[] = [
  { path: '/login', element: wrap(<LoginPage />) },
  // v1 (2026-07, issue #206): e2e 测试路由 — 脱离 AppLayout/RequireAuth，独立渲染 WorkflowEditor
  { path: '/e2e/workflow-editor', element: wrap(<E2EWorkflowEditorPage />) },
  // v1 (2026-07, issue #206): e2e 测试路由 — PipelineDetailPage 集成测试
  { path: '/e2e/pipeline-detail', element: wrap(<E2EPipelineDetailPage />) },
  {
    element: <AppLayoutWithOutlet />,
    children: [
      { path: '/', element: <Navigate to="/dashboard" replace /> },
      { path: '/dashboard', element: wrap(<DashboardPage />) },
      {
        element: <RequireAuth />,
        children: [
          { path: '/pipelines', element: wrap(<PipelineListPage />) },
          { path: '/pipelines/:projectId/_file_/*', element: wrap(<PipelineDetailPage />) },
          { path: '/pipelines/:projectId/:definitionId', element: wrap(<PipelineDetailPage />) },
          { path: '/runs', element: wrap(<RunListPage />) },
          { path: '/runs/:id', element: wrap(<RunDetailPage />) },
          { path: '/servers', element: wrap(<ServersPage />) },
          { path: '/plugins', element: wrap(<PluginListPage />) },
        ],
      },
    ],
  },
];

export default routes;
