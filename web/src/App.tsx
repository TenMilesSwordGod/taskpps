import { useRoutes } from 'react-router-dom';
import routes from '@/routes';
import ErrorBoundary from '@/components/ErrorBoundary';

/**
 * 应用根组件。
 *
 * v1 (2026-07, issue #204): 移除顶层 <AppLayout> 包裹。
 * AppLayout 现作为 layout route 嵌入 routes.tsx，使 /login 可独立渲染（无侧边栏），
 * 受保护路由由 RequireAuth 守卫。
 * v2 (2026-09, issue #213): 用全局 ErrorBoundary 包裹路由出口，
 * 页面渲染异常/懒加载 chunk 失败时展示兜底而不是整页白屏。
 */
export default function App() {
  const element = useRoutes(routes);
  return <ErrorBoundary>{element}</ErrorBoundary>;
}
