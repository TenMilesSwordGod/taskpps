import { createContext, useContext } from 'react';

/**
 * 只读模式上下文
 *
 * 设计决策：将 readOnly 通过 React Context 而非 props 传递到节点组件，
 * 因为 ReactFlow 的 nodeTypes 是静态注册的，不支持向节点组件注入
 * 动态 props。使用 Context 可以避免在 WorkflowEditor ↔ 节点之间
 * 产生循环依赖（WorkflowEditor 导入节点类型，节点类型导入 Context
 * 所在文件而非 WorkflowEditor 本身）。
 */
export const ReadOnlyCtx = createContext(false);

/** 获取当前画布的只读状态 */
export function useReadOnly(): boolean {
  return useContext(ReadOnlyCtx);
}
