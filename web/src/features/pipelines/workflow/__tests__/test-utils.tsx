import { type ReactElement } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';

/**
 * 测试工具：用 ReactFlowProvider 包裹组件
 * React Flow 的 Handle 等组件需要使用 useStoreApi()，
 * 必须在 ReactFlowProvider 上下文中渲染
 * 
 * 用于独立测试节点组件（不依赖完整 WorkflowEditor 画布）
 */
function WithReactFlowProvider({ children }: { children: React.ReactNode }) {
  return <ReactFlowProvider>{children}</ReactFlowProvider>;
}

/** 带 ReactFlowProvider 的 render 函数 */
export function renderWithProvider(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
) {
  return render(ui, { wrapper: WithReactFlowProvider, ...options });
}
