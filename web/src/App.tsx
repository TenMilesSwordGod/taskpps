import { useRoutes } from 'react-router-dom';
import routes from '@/routes';

/**
 * 应用根组件。
 *
 * v1 (2026-07, issue #204): 移除顶层 <AppLayout> 包裹。
 * AppLayout 现作为 layout route 嵌入 routes.tsx，使 /login 可独立渲染（无侧边栏），
 * 受保护路由由 RequireAuth 守卫。
 */
export default function App() {
  return useRoutes(routes);
}
