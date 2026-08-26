import type { EdgeChange, NodeChange } from '@xyflow/react';

/**
 * v6 (2026-08): critique P1 — 内容性变化判定。
 *
 * 为什么需要：React Flow 的内部测量（dimensions）与选择态（select）也会走
 * onNodesChange/onEdgesChange 回调，此前一律 setIsDirty(true) 导致「进入编辑模式
 * 未动一笔即假报有未保存的修改」，稀释了真实警告的可信度。
 *
 * 判定规则：
 *   - 节点变化中 select / dimensions 不算内容变化；
 *   - 边变化中 select 不算内容变化（边没有 dimensions 概念）；
 *   - 其余（position/add/remove/replace）都代表图内容被用户改变。
 */
export function isContentChange(changes: Array<NodeChange | EdgeChange>): boolean {
  return changes.some(
    (c) => c.type !== 'select' && c.type !== 'dimensions',
  );
}
