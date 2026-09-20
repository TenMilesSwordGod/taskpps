import type { Node } from '@xyflow/react';
import type { EditorNodeData } from './yamlToNodes';

/**
 * 容器折叠/展开工具
 *
 * v1 (2026-07): 从 WorkflowEditor / EditorSubPipelineNode 两处重复逻辑中提取。
 * 修复两个压测暴露的问题：
 *   1. 折叠后子节点仍在渲染并溢出紧凑容器 → 折叠时隐藏全部后代节点
 *   2. 展开时 style 已被折叠尺寸覆盖，容器恢复不了原尺寸 → 折叠前把原 style
 *      存入 data.__expandedStyle，展开时恢复
 * 布局侧配合：layoutGraph 对 collapsed 容器不递归布局内部，保持折叠尺寸，
 * 避免点击"布局"把折叠容器撑开。
 */

/** 折叠态紧凑尺寸 */
export const COLLAPSED_SIZE = { width: 140, height: 48 };

/** 沿 parentId 链判断 node 是否为 containerId 的后代 */
function isDescendantOf<N extends Node>(
  node: N,
  containerId: string,
  nodeMap: Map<string, N>,
): boolean {
  let cur = node.parentId ? nodeMap.get(node.parentId) : undefined;
  while (cur) {
    if (cur.id === containerId) return true;
    cur = cur.parentId ? nodeMap.get(cur.parentId) : undefined;
  }
  return false;
}

/**
 * 折叠/展开容器，返回新的节点数组（不修改输入）。
 *
 * @param collapse true=折叠，false=展开
 */
export function applyCollapse<N extends Node>(
  nodes: N[],
  containerId: string,
  collapse: boolean,
): N[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  return nodes.map((n) => {
    if (n.id === containerId) {
      const data = { ...(n.data as Record<string, unknown> | undefined) };
      const expandedStyle = (data.__expandedStyle as object | undefined) ?? n.style;
      if (collapse) {
        // 保存折叠前尺寸，供展开恢复
        data.__expandedStyle = n.style;
        data.collapsed = true;
      } else {
        delete data.__expandedStyle;
        data.collapsed = false;
      }
      return {
        ...n,
        data,
        style: collapse ? { ...((n.style as object) ?? {}), ...COLLAPSED_SIZE } : expandedStyle,
      } as N;
    }
    if (isDescendantOf(n, containerId, nodeMap)) {
      return { ...n, hidden: collapse };
    }
    return n;
  });
}

/** 读取节点当前的折叠状态 */
export function isCollapsed(node: Node<EditorNodeData> | undefined): boolean {
  return node?.data?.collapsed === true;
}
