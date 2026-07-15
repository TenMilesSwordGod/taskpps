import { useCallback, useRef } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  type NodeMouseHandler,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import TaskNode from './nodes/TaskNode';
import SubpipelineGroupNode from './nodes/SubpipelineGroupNode';
import PostTaskNode from './nodes/PostTaskNode';
import { StartNode, EndNode } from './nodes/StartEndNode';
import DecisionNode from './nodes/DecisionNode';
import { usePipelineGraph } from './hooks/usePipelineGraph';
import { useAppStore } from '@/stores/appStore';
import { TYPE_COLOR, STATUS_COLOR, INK } from './nodes/nodeTokens';
import type { PipelineDetail, TaskStatus, TaskType } from '@/types';

/** Start/End 节点包装组件 */
function StartEndNodeWrapper(props: { data: { variant: 'start' | 'end'; [key: string]: unknown } }) {
  return props.data.variant === 'start'
    ? <StartNode data={props.data as { variant: 'start' }} />
    : <EndNode data={props.data as { variant: 'end' }} />;
}

/** 注册自定义节点类型 */
const nodeTypes = {
  taskNode: TaskNode,
  subpipelineGroup: SubpipelineGroupNode,
  postTask: PostTaskNode,
  startEnd: StartEndNodeWrapper,
  decisionNode: DecisionNode,
};

/** MiniMap 节点颜色 —— 按类型/状态着色，与节点强调色一致 */
function miniMapNodeColor(node: Node): string {
  if (node.type === 'startEnd') {
    return node.data?.variant === 'start' ? '#10B981' : '#94A3B8';
  }
  if (node.type === 'decisionNode') return '#FDBA74';
  if (node.type === 'subpipelineGroup') return '#E2E8F0';
  if (node.type === 'postTask') return '#CBD5E1';
  if (node.type === 'taskNode') {
    const status = node.data?.status as TaskStatus | undefined;
    if (status) return STATUS_COLOR[status];
    const task = node.data?.task as { invoke?: unknown; steps?: unknown; plugin?: unknown; git?: unknown; nexus?: unknown } | undefined;
    let taskType: TaskType = 'command';
    if (task?.invoke) taskType = 'invoke';
    else if (task?.steps) taskType = 'steps';
    else if (task?.plugin) taskType = 'plugin';
    else if (task?.git) taskType = 'git';
    else if (task?.nexus) taskType = 'nexus';
    return TYPE_COLOR[taskType];
  }
  return '#CBD5E1';
}

/** 拖拽放置回调数据 */
export interface DropData {
  taskType: string;
  label: string;
  color: string;
}

interface PipelineGraphProps {
  pipeline: PipelineDetail | undefined;
  taskStatuses?: Record<string, TaskStatus>;
  /** 外部传入的当前任务 ID（用于同步树形选择） */
  selectedTaskId?: string | null;
  /** 点击节点回调 */
  onNodeClick?: (taskId: string) => void;
  /** 是否处于编辑模式 */
  editMode?: boolean;
  /** 拖拽放置回调（编辑模式下从 NodePanel 拖入节点时触发） */
  onNodeDrop?: (data: DropData, position: { x: number; y: number }) => void;
}

/** DAG 画布组件，封装 ReactFlow —— 工程蓝图风格 */
export default function PipelineGraph({ pipeline, taskStatuses, selectedTaskId, onNodeClick, editMode = false, onNodeDrop }: PipelineGraphProps) {
  const { nodes, edges } = usePipelineGraph({ pipeline, taskStatuses });
  const setSelectedNodeId = useAppStore((s) => s.setSelectedNodeId);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const reactFlowInstanceRef = useRef<ReactFlowInstance | null>(null);

  /** editMode 下允许在画布上放置从 NodePanel 拖入的节点 */
  const onDragOverHandler = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
    },
    [],
  );

  const onDropHandler = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      if (!editMode) return;
      const raw = event.dataTransfer.getData('application/reactflow');
      if (!raw) return;
      try {
        const data: DropData = JSON.parse(raw);
        const instance = reactFlowInstanceRef.current;
        if (!instance) return;
        const position = instance.screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });
        onNodeDrop?.(data, position);
      } catch {
        // 忽略非法拖拽数据
      }
    },
    [editMode, onNodeDrop],
  );

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
    <div
      ref={wrapperRef}
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: INK.canvas,
      }}
    >
      <ReactFlow
        nodes={syncedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={onPaneClick}
        onDragOver={editMode ? onDragOverHandler : undefined}
        onDrop={editMode ? onDropHandler : undefined}
        onInit={(instance) => { reactFlowInstanceRef.current = instance; }}
        fitView
        fitViewOptions={{ padding: 0.3, includeHiddenNodes: false }}
        onlyRenderVisibleElements
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: 'smoothstep' }}
        nodesDraggable={editMode}
        nodesConnectable={editMode}
      >
        {/* 点状网格背景 —— 工程蓝图栅格 */}
        <Background
          variant={BackgroundVariant.Dots}
          gap={18}
          size={1}
          color="#CBD5E1"
        />
        <Controls
          className="!shadow-sm !border !border-slate-200 !rounded !overflow-hidden"
          showInteractive={false}
        />
        <MiniMap
          nodeStrokeWidth={2}
          nodeColor={miniMapNodeColor}
          nodeStrokeColor="#fff"
          maskColor="rgba(241, 245, 249, 0.6)"
          className="!shadow-sm !border !border-slate-200 !rounded !overflow-hidden"
          position="bottom-left"
          zoomable
          pannable
        />
      </ReactFlow>
    </div>
  );
}
