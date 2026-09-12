import { useMe } from '@/api/auth';

/**
 * 是否管理员。
 *
 * 设计决策：独立成 hook 而不是在组件里直接 useMe()，一是 ServersPage/弹窗多处需要，
 * 二是测试可单独 mock（避免每个用例都构造 /me 查询），保持权限判断只有一个来源。
 */
export function useIsAdmin(): boolean {
  const { data } = useMe();
  return data?.role === 'admin';
}
