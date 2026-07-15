import { lazy, Suspense } from 'react';
import type { RouteObject } from 'react-router-dom';
import { Spin } from 'antd';

// 路由级 code splitting：每个页面单独 chunk，首屏只下载必要的
const DashboardPage = lazy(() => import('@/features/dashboard/DashboardPage'));
const PipelineListPage = lazy(() => import('@/features/pipelines/PipelineListPage'));
const PipelineDetailPage = lazy(() => import('@/features/pipelines/PipelineDetailPage'));
const RunListPage = lazy(() => import('@/features/runs/RunListPage'));
const RunDetailPage = lazy(() => import('@/features/runs/RunDetailPage'));
const ServersPage = lazy(() => import('@/features/servers/ServersPage'));
const PluginListPage = lazy(() => import('@/features/plugins/PluginListPage'));

/** 路由级 Suspense fallback */
function RouteFallback() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
      <Spin size="large" />
    </div>
  );
}

const wrap = (el: React.ReactNode) => <Suspense fallback={<RouteFallback />}>{el}</Suspense>;

/** 路由定义 */
const routes: RouteObject[] = [
  { path: '/', element: wrap(<DashboardPage />) },
  { path: '/pipelines', element: wrap(<PipelineListPage />) },
  { path: '/pipelines/:projectId/_file_/*', element: wrap(<PipelineDetailPage />) },
  { path: '/pipelines/:projectId/:definitionId', element: wrap(<PipelineDetailPage />) },
  { path: '/runs', element: wrap(<RunListPage />) },
  { path: '/runs/:id', element: wrap(<RunDetailPage />) },
  { path: '/servers', element: wrap(<ServersPage />) },
  { path: '/plugins', element: wrap(<PluginListPage />) },
];

export default routes;
