import { useCallback, useMemo, useRef, DragEvent } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { message } from 'antd';
import EditorTaskNode from './nodes/EditorTaskNode';
import EditorSubPipelineNode from './nodes/EditorSubPipelineNode';
import EditorPostParentNode from './nodes/EditorPostParentNode';
import EditorPostChildNode from './nodes/EditorPostChildNode';
import EditorStartEndNode from './nodes/EditorStartEndNode';
import EditorPipelineNode from './nodes/EditorPipelineNode';
import { yamlToNodes } from './yamlToNodes';
import type { EditorNodeData, EditorEdgeData } from './yamlToNodes';
import type { PipelineDetail } from '@/types';
import { INK } from '@/features/pipelines/nodes/nodeTokens';
import { applyDagreLayout } from '@/utils/dagreLayout';

/**
 * 可编辑工作流画布组件
 * 将只读 PipelineGraph 升级为 n8n 式可编辑画布
 *
 * 支持:
 *   - 节点拖拽/缩放/平移
 *   - 端口连线（in/out/post）
 *   - 来自 NodePalette 的拖拽新增节点
 *   - 选中节点触发 PropertyPanel
 *   - YAML 双向同步
 */

const NODE_TYPES: NodeTypes = {
  editorTask: EditorTaskNode,
  editorSubPipeline: EditorSubPipelineNode,
  editorPostParent: EditorPostParentNode,
  editorPostChild: EditorPostChildNode,
  editorStartEnd: EditorStartEndNode,
  editorPipeline: EditorPipelineNode,
};

interface WorkflowEditorProps {
  pipeline?: PipelineDetail;
  taskStatuses?: Record<string, unknown>;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string | null) => void;
  onGraphChange?: (nodes: Node<EditorNodeData>[], edges: Edge<EditorEdgeData>[]) => void;
  readOnly?: boolean;
}

export default function WorkflowEditor({
  pipeline,
  selectedNodeId,
  onNodeSelect,
  onGraphChange,
  readOnly = false,
}: WorkflowEditorProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useRef<unknown>(null);

  // 从 pipeline 解析初始 nodes/edges
  const initialGraph = useMemo(() => {
    if (!pipeline) return { nodes: [] as Node<EditorNodeData>[], edges: [] as Edge<EditorEdgeData>[] };
    return yamlToNodes(pipeline);
  }, [pipeline]);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<EditorNodeData>>(initialGraph.nodes as Node<EditorNodeData>[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<EditorEdgeData>>(initialGraph.edges as Edge<EditorEdgeData>[]);

  // 当 pipeline 改变时重置状态
  useMemo(() => {
    setNodes(initialGraph.nodes);
    setEdges(initialGraph.edges);
  }, [pipeline?.name, pipeline?.pipelines?.length]);

  // 通知父组件 graph 变化
  const handleGraphChange = useCallback(() => {
    onGraphChange?.(nodes, edges);
  }, [nodes, edges, onGraphChange]);

  // 连线处理
  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;

      // 检查源和目标不能相同
      if (connection.source === connection.target) return;

      setEdges((eds: Edge<EditorEdgeData>[]) => addEdge({
        ...connection,
        type: 'smoothstep',
        markerEnd: { type: 'arrowclosed' as const, width: 8, height: 8, color: '#94a3b8' },
        style: { stroke: '#94a3b8', strokeWidth: 2 },
        data: {
          edgeType: 'explicit',
          explicit: true,
          implicit: false,
        },
      } as Edge<EditorEdgeData>, eds));
    },
    [readOnly, setEdges],
  );

  // 节点变化处理
  const handleNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (readOnly) return;
      onNodesChange(changes);
    },
    [readOnly, onNodesChange],
  );

  // 边变化处理
  const handleEdgesChange = useCallback(
    (changes: Parameters<OnEdgesChange>[0]) => {
      if (readOnly) return;
      onEdgesChange(changes as never);
    },
    [readOnly, onEdgesChange],
  );

  // 节点点击 → 选中
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeSelect(node.id);
    },
    [onNodeSelect],
  );

  // 画布空白点击 → 取消选中
  const handlePaneClick = useCallback(() => {
    onNodeSelect(null);
  }, [onNodeSelect]);

  // 拖拽新增节点（来自 NodePalette）
  const handleDragOver = useCallback((event: DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent) => {
      event.preventDefault();

      const typeData = event.dataTransfer.getData('application/reactflow-type');
      const nodeTypeName = event.dataTransfer.getData('application/reactflow-node-type');
      const label = event.dataTransfer.getData('application/reactflow-label');

      if (!typeData) return;

      const wrapperEl = wrapperRef.current;
      if (!wrapperEl) return;

      const bounds = wrapperEl.getBoundingClientRect();
      const wrapperScrollLeft = wrapperEl.scrollLeft || 0;
      const wrapperScrollTop = wrapperEl.scrollTop || 0;

      // 计算相对于画布的位置（考虑平移和缩放）
      const position = {
        x: event.clientX - bounds.left + wrapperScrollLeft - 90,
        y: event.clientY - bounds.top + wrapperScrollTop - 28,
      };

      // 生成节点 ID
      const nodeId = `__new__${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

      if (nodeTypeName === 'subpipeline') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorSubPipeline',
          position,
          style: { width: 260, height: 140 },
          data: {
            label: label || '新 SubPipeline',
            executionStrategy: 'sequential',
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
      } else if (nodeTypeName === 'task') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorTask',
          position,
          data: {
            task: { name: label || '新 Task', env: {}, retry: 0, depends_on: [] },
            taskType: 'command',
            subpipelineName: '',
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
      } else if (nodeTypeName === 'post_parent') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorPostParent',
          position,
          style: { width: 280, height: 150 },
          data: { label: label || 'Post 处理容器' },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
      } else if (nodeTypeName === 'post_child') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorPostChild',
          position,
          data: {
            task: { name: label || '新 Post Task', env: {}, retry: 0, depends_on: [] },
            taskType: 'command',
            postVariant: 'on_fail',
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
      }

      message.success(`已添加节点: ${label || nodeTypeName}`);
    },
    [setNodes],
  );

  // 同步选中状态到节点
  const syncedNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        selected: n.id === selectedNodeId,
      })),
    [nodes, selectedNodeId],
  );

  return (
    <div
      ref={wrapperRef}
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: '#f5f5f5',
      }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <ReactFlow
        nodes={syncedNodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.3, includeHiddenNodes: false }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: 'smoothstep',
        }}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
      >
        {/* 浅灰微点网格背景 */}
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#e5e5e5"
        />
        <Controls
          className="!shadow-sm !border !border-slate-200 !rounded !overflow-hidden"
          showInteractive={false}
        />
        <MiniMap
          nodeStrokeWidth={2}
          nodeColor={miniMapColor}
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

/** MiniMap 节点着色 */
function miniMapColor(node: Node): string {
  if (node.type === 'editorStartEnd') {
    return node.data?.variant === 'start' ? '#10B981' : '#94A3B8';
  }
  if (node.type === 'editorSubPipeline') return '#dbeafe';
  if (node.type === 'editorPostParent') return '#fecaca';
  if (node.type === 'editorPostChild') return '#fef2f2';
  if (node.type === 'editorTask') return '#dcfce7';
  if (node.type === 'editorPipeline') return '#f8fafc';
  return '#CBD5E1';
}
