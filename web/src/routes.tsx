import type { RouteObject } from 'react-router-dom';
import DashboardPage from '@/features/dashboard/DashboardPage';
import PipelineListPage from '@/features/pipelines/PipelineListPage';
import PipelineDetailPage from '@/features/pipelines/PipelineDetailPage';
import RunListPage from '@/features/runs/RunListPage';
import RunDetailPage from '@/features/runs/RunDetailPage';

/** 路由定义 */
const routes: RouteObject[] = [
  {
    path: '/',
    element: <DashboardPage />,
  },
  {
    path: '/pipelines',
    element: <PipelineListPage />,
  },
  {
    path: '/pipelines/:file',
    element: <PipelineDetailPage />,
  },
  {
    path: '/runs',
    element: <RunListPage />,
  },
  {
    path: '/runs/:id',
    element: <RunDetailPage />,
  },
];

export default routes;
