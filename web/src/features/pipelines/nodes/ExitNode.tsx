import { Handle, Position } from '@xyflow/react';

/**
 * 不可见的 exit 汇聚节点 —— 仅作为边连接锚点。
 * 位于分组内容区域内部，使 no/alt/末 task 边在分组内终止，不穿出底部边框。
 * 渲染为空（0×0），但 Handle 仍可被边连接。
 */
export default function ExitNode() {
  return (
    <Handle
      type="target"
      position={Position.Top}
      style={{ width: 0, height: 0, border: 'none', background: 'transparent' }}
    />
  );
}
