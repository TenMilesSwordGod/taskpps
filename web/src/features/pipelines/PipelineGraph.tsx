import { useCallback, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import TaskNode from './nodes/TaskNode';
import SubpipelineGroupNode from './nodes/SubpipelineGroupNode';
import { usePipelineGraph } from './hooks/usePipelineGraph';
import { useAppStore } from '@/stores/appStore';
import type { PipelineDetail, TaskStatus } from '@/types';

/** 注册自定义节点类型 */
const nodeTypes = {
  taskNode: TaskNode,
  subpipelineGroup: SubpipelineGroupNode,
};

interface PipelineGraphProps {
  pipeline: PipelineDetail | undefined;
  taskStatuses?: Record<string, TaskStatus>;
  /** 外部传入的当前任务 ID（用于同步树形选择） */
  selectedTaskId?: string | null;
  /** 点击节点回调 */
  onNodeClick?: (taskId: string) => void;
}

/** DAG 画布组件，封装 ReactFlow */
export default function PipelineGraph({ pipeline, taskStatuses, selectedTaskId, onNodeClick }: PipelineGraphProps) {
  const { nodes, edges } = usePipelineGraph({ pipeline, taskStatuses });
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      if (node.type === 'taskNode' || node.type === 'subpipelineGroup') {
        setSelectedNodeId(node.id);
        onNodeClick?.(node.id);
      }
    },
    [setSelectedNodeId, onNodeClick],
  );

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
    onNodeClick?.('');
  }, [setSelectedNodeId, onNodeClick]);

  // 同步外部选中状态到 store
  const syncedNodes = selectedTaskId !== undefined
    ? nodes.map((n) => ({ ...n, selected: n.id === selectedTaskId }))
    : nodes;

  return (
    <div ref={wrapperRef} style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={syncedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={onPaneClick}
        fitView
        onlyRenderVisibleElements
        minZoom={0.1}
        maxZoom={2}
      >
        <Background />
        <Controls />
        <MiniMap
          nodeStrokeWidth={3}
          zoomable
          pannable
        />
      </ReactFlow>
    </div>
  );
}
