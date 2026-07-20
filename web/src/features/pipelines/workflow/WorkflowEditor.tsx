import { useCallback, useMemo, useRef, DragEvent, useState } from 'react';
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
  type NodeMouseHandler,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { message, Tooltip, Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { SaveOutlined, ApartmentOutlined, ExpandOutlined, CameraOutlined } from '@ant-design/icons';
import EditorTaskNode from './nodes/EditorTaskNode';
import EditorSubPipelineNode from './nodes/EditorSubPipelineNode';
import EditorPostParentNode from './nodes/EditorPostParentNode';
import EditorPostChildNode from './nodes/EditorPostChildNode';
import EditorStartEndNode from './nodes/EditorStartEndNode';
import EditorPipelineNode from './nodes/EditorPipelineNode';
import { yamlToNodes } from './yamlToNodes';
import type { EditorNodeData, EditorEdgeData } from './yamlToNodes';
import type { PipelineDetail } from '@/types';
import { applyDagreLayout } from '@/utils/dagreLayout';
import { validateDrop, findDropParentContext } from './validateDrop';

/**
 * 可编辑工作流画布组件
 * 将只读 PipelineGraph 升级为 n8n 式可编辑画布
 *
 * 支持:
 *   - 节点拖拽/缩放/平移
 *   - 端口连线（in/out/post）
 *   - 来自 NodePalette 的拖拽新增节点（含容器嵌套校验）
 *   - 选中节点触发 PropertyPanel
 *   - 右键菜单（节点上下文 + 画布上下文）
 *   - 容器折叠/展开
 *   - 工具栏（保存/自动布局/适应窗口/导出图片）
 *   - YAML 双向同步
 *
 * v2 (2026-07): 补充 5 项功能—handleDrop校验 + 右键菜单 + 折叠展开 + 工具栏 + SVG图标
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

/** 右键菜单状态 */
interface ContextMenuState {
  open: boolean;
  x: number;
  y: number;
  type: 'pane' | 'node';
  nodeId?: string;
  nodeType?: string;
}

export default function WorkflowEditor({
  pipeline,
  selectedNodeId,
  onNodeSelect,
  onGraphChange,
  readOnly = false,
}: WorkflowEditorProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const reactFlowInstanceRef = useRef<ReactFlowInstance | null>(null);

  // 追踪画布是否有未保存修改
  const [isDirty, setIsDirty] = useState(false);

  // 右键菜单状态
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  // 从 pipeline 解析初始 nodes/edges
  const initialGraph = useMemo(() => {
    if (!pipeline) return { nodes: [] as Node<EditorNodeData>[], edges: [] as Edge<EditorEdgeData>[] };
    return yamlToNodes(pipeline);
  }, [pipeline]);

  const [nodes, setNodes, onNodesChangeRaw] = useNodesState<Node<EditorNodeData>>(initialGraph.nodes as Node<EditorNodeData>[]);
  const [edges, setEdges, onEdgesChangeRaw] = useEdgesState<Edge<EditorEdgeData>>(initialGraph.edges as Edge<EditorEdgeData>[]);

  // 当 pipeline 改变时重置状态
  useMemo(() => {
    setNodes(initialGraph.nodes);
    setEdges(initialGraph.edges);
    setIsDirty(false);
  }, [pipeline?.name, pipeline?.pipelines?.length]);

  // 通知父组件 graph 变化
  const handleGraphChange = useCallback(() => {
    onGraphChange?.(nodes, edges);
  }, [nodes, edges, onGraphChange]);

  // 连线处理
  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
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

  // 节点变化处理 — 标记 dirty
  const handleNodesChange: OnNodesChange = useCallback(
    (changes) => {
      if (readOnly) return;
      onNodesChangeRaw(changes);
      setIsDirty(true);
    },
    [readOnly, onNodesChangeRaw],
  );

  // 边变化处理 — 标记 dirty
  const handleEdgesChange = useCallback(
    (changes: Parameters<OnEdgesChange>[0]) => {
      if (readOnly) return;
      onEdgesChangeRaw(changes as never);
      setIsDirty(true);
    },
    [readOnly, onEdgesChangeRaw],
  );

  // 节点点击 → 选中
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeSelect(node.id);
    },
    [onNodeSelect],
  );

  // 画布空白点击 → 取消选中 + 关闭右键菜单
  const handlePaneClick = useCallback(() => {
    onNodeSelect(null);
    setContextMenu(null);
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

      // v2 (2026-07): 用 screenToFlowPosition 将屏幕坐标转为画布坐标（考虑缩放/平移）
      const flowPosition = reactFlowInstanceRef.current?.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      if (!flowPosition) return;

      // v3 (2026-07): 动态计算 drop 位置下的实际父容器上下文
      // 原实现硬编码 'canvas-root'，导致拖入 SubPipeline 内部时校验规则不生效
      const { context: parentContext, parentId: containerParentId } = findDropParentContext(flowPosition, nodes);

      const validationError = validateDrop(nodeTypeName, parentContext, nodes);
      if (validationError) {
        message.error(validationError);
        return;
      }

      // v2 (2026-07): screenToFlowPosition 替代手动 clientX/Y 偏移计算（更准确，考虑 zoom/pan）
      const position = {
        x: flowPosition.x - 90,
        y: flowPosition.y - 28,
      };

      const nodeId = `__new__${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

      // v3 (2026-07): 若 drop 在容器内部，设置 parentId 并调整坐标为相对容器坐标
      // ReactFlow parentId 机制要求子节点 position 相对于父容器节点
      let nodePosition = { x: position.x, y: position.y };
      let nodeParentId: string | undefined;
      if (containerParentId) {
        const container = nodes.find((n) => n.id === containerParentId);
        if (container) {
          nodePosition = {
            x: position.x - container.position.x,
            y: position.y - container.position.y,
          };
          nodeParentId = containerParentId;
        }
      }

      if (nodeTypeName === 'subpipeline') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorSubPipeline',
          position: nodePosition,
          parentId: nodeParentId,
          style: { width: 260, height: 140 },
          data: {
            label: label || '新 SubPipeline',
            executionStrategy: 'sequential',
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
        setIsDirty(true);
      } else if (nodeTypeName === 'task') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorTask',
          position: nodePosition,
          parentId: nodeParentId,
          data: {
            task: { name: label || '新 Task', env: {}, retry: 0, depends_on: [] },
            taskType: 'command',
            subpipelineName: '',
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
        setIsDirty(true);
      } else if (nodeTypeName === 'post_parent') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorPostParent',
          position: nodePosition,
          parentId: nodeParentId,
          style: { width: 280, height: 150 },
          data: { label: label || 'Post 处理容器' },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
        setIsDirty(true);
      } else if (nodeTypeName.startsWith('post_child_')) {
        const variantMap: Record<string, 'on_fail' | 'on_success' | 'always'> = {
          post_child_on_fail: 'on_fail',
          post_child_on_success: 'on_success',
          post_child_always: 'always',
        };
        const postVariant = variantMap[nodeTypeName] || 'on_fail';
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorPostChild',
          position: nodePosition,
          parentId: nodeParentId,
          data: {
            task: { name: label || '新 Post Task', env: {}, retry: 0, depends_on: [] },
            taskType: 'command',
            postVariant,
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
        setIsDirty(true);
      } else if (nodeTypeName === 'startend') {
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorStartEnd',
          position: nodePosition,
          parentId: nodeParentId,
          data: { variant: 'start' },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
        setIsDirty(true);
      } else if (nodeTypeName.startsWith('task_atomic_')) {
        const typeMap: Record<string, 'command' | 'steps' | 'plugin' | 'invoke'> = {
          task_atomic_cmd: 'command',
          task_atomic_step: 'steps',
          task_atomic_plugin: 'plugin',
          task_atomic_invoke: 'invoke',
        };
        const taskType = typeMap[nodeTypeName] || 'command';
        const newNode: Node<EditorNodeData> = {
          id: nodeId,
          type: 'editorTask',
          position: nodePosition,
          parentId: nodeParentId,
          data: {
            task: { name: label || '新任务', env: {}, retry: 0, depends_on: [] },
            taskType,
            subpipelineName: '',
          },
        };
        setNodes((nds: Node<EditorNodeData>[]) => [...nds, newNode]);
        setIsDirty(true);
      }

      message.success(`已添加节点: ${label || nodeTypeName}`);
    },
    [setNodes, nodes],
  );

  // === 右键菜单处理 ===
  // v2 (2026-07): 三种右键上下文 — 画布空白/SubPipeline内部/Post父容器内部

  const handleNodeContextMenu: NodeMouseHandler = useCallback(
    (event, node) => {
      event.preventDefault();
      if (readOnly) return;

      setContextMenu({
        open: true,
        x: event.clientX,
        y: event.clientY,
        type: 'node',
        nodeId: node.id,
        nodeType: node.type ?? undefined,
      });
    },
    [readOnly],
  );

  const handlePaneContextMenu = useCallback(
    (event: React.MouseEvent | MouseEvent) => {
      event.preventDefault();
      if (readOnly) return;

      setContextMenu({
        open: true,
        x: (event as MouseEvent).clientX,
        y: (event as MouseEvent).clientY,
        type: 'pane',
      });
    },
    [readOnly],
  );

  const handleCloseContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  // 删除节点
  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      if (selectedNodeId === nodeId) {
        onNodeSelect(null);
      }
      setIsDirty(true);
      message.success('节点已删除');
      setContextMenu(null);
    },
    [setNodes, setEdges, selectedNodeId, onNodeSelect],
  );

  // 折叠/展开节点
  const handleToggleCollapse = useCallback(
    (nodeId: string) => {
      setNodes((nds) =>
        nds.map((n) => {
          if (n.id !== nodeId) return n;
          const collapsed = !n.data?.collapsed;
          return {
            ...n,
            data: { ...n.data, collapsed },
            style: collapsed
              ? { ...(n.style as object), width: 140, height: 48 }
              : n.style,
          };
        }),
      );
      setIsDirty(false); // 折叠不影响 YAML，不标 dirty
      setContextMenu(null);
    },
    [setNodes],
  );

  // 查看节点属性（选中节点）
  const handleNodeProperties = useCallback(
    (nodeId: string) => {
      onNodeSelect(nodeId);
      setContextMenu(null);
    },
    [onNodeSelect],
  );

  // 从画布右键菜单添加节点
  const handleAddNodeFromContext = useCallback(
    (nodeTypeName: string) => {
      const validationError = validateDrop(nodeTypeName, 'canvas-root', nodes);
      if (validationError) {
        message.error(validationError);
        setContextMenu(null);
        return;
      }

      const nodeId = `__new__${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const position = { x: 200, y: 200 };

      if (nodeTypeName === 'subpipeline') {
        setNodes((nds) => [...nds, {
          id: nodeId, type: 'editorSubPipeline', position,
          style: { width: 260, height: 140 },
          data: { label: '新 SubPipeline', executionStrategy: 'sequential' },
        } as Node<EditorNodeData>]);
      } else if (nodeTypeName === 'task') {
        setNodes((nds) => [...nds, {
          id: nodeId, type: 'editorTask', position,
          data: { task: { name: '新 Task', env: {}, retry: 0, depends_on: [] }, taskType: 'command', subpipelineName: '' },
        } as Node<EditorNodeData>]);
      } else if (nodeTypeName === 'post_parent') {
        setNodes((nds) => [...nds, {
          id: nodeId, type: 'editorPostParent', position,
          style: { width: 280, height: 150 },
          data: { label: 'Post 处理容器' },
        } as Node<EditorNodeData>]);
      } else if (nodeTypeName === 'startend') {
        setNodes((nds) => [...nds, {
          id: nodeId, type: 'editorStartEnd', position,
          data: { variant: 'start' },
        } as Node<EditorNodeData>]);
      }
      setIsDirty(true);
      message.success(`已添加节点: ${nodeTypeName}`);
      setContextMenu(null);
    },
    [setNodes, nodes],
  );

  // === 工具栏操作 ===

  const handleSave = useCallback(() => {
    handleGraphChange();
    setIsDirty(false);
    message.success('工作流已保存');
  }, [handleGraphChange]);

  const handleAutoLayout = useCallback(() => {
    try {
      const layouted = applyDagreLayout(
        nodes as unknown as Node<Record<string, unknown>>[],
        edges as unknown as Edge<Record<string, unknown>>[],
      );
      setNodes(layouted as unknown as Node<EditorNodeData>[]);
      setIsDirty(true);
      message.success('自动布局完成');
    } catch {
      message.error('自动布局失败');
    }
  }, [nodes, edges, setNodes]);

  const handleFitView = useCallback(() => {
    reactFlowInstanceRef.current?.fitView({ padding: 0.3, duration: 300 });
  }, []);

  const handleExportImage = useCallback(async () => {
    message.info('导出图片功能准备中...');
  }, []);

  // 构建右键菜单项
  const contextMenuItems: MenuProps['items'] = useMemo(() => {
    if (!contextMenu) return [];

    if (contextMenu.type === 'pane') {
      // 画布空白处右键 — 添加节点
      const hasBoth = nodes.some(n => n.id === '__start__') && nodes.some(n => n.id === '__end__');
      return [
        { key: 'add-subpipeline', label: '添加 SubPipeline', onClick: () => handleAddNodeFromContext('subpipeline') },
        { key: 'add-task', label: '添加 Task', onClick: () => handleAddNodeFromContext('task') },
        { key: 'add-post-parent', label: '添加 Post 父容器', onClick: () => handleAddNodeFromContext('post_parent') },
        {
          key: 'add-start',
          label: hasBoth ? '添加 Start/End（已存在）' : '添加 Start/End',
          disabled: hasBoth,
          onClick: () => handleAddNodeFromContext('startend'),
        },
      ];
    }

    if (contextMenu.type === 'node') {
      const node = nodes.find(n => n.id === contextMenu.nodeId);
      const isContainer = node?.type === 'editorSubPipeline' || node?.type === 'editorTask' || node?.type === 'editorPostParent';
      const isCollapsed = node?.data?.collapsed === true;
      const items: MenuProps['items'] = [];

      // SubPipeline 内部右键 — 添加 Task
      if (node?.type === 'editorSubPipeline') {
        items.push({ key: 'add-task-inside', label: '添加 Task', onClick: () => handleAddNodeFromContext('task') });
      }

      // Post 父容器内部右键 — 添加 Post 子容器
      if (node?.type === 'editorPostParent') {
        const hasOnFail = nodes.some(n => n.type === 'editorPostChild' && n.data?.postVariant === 'on_fail');
        const hasOnSuccess = nodes.some(n => n.type === 'editorPostChild' && n.data?.postVariant === 'on_success');
        const hasAlways = nodes.some(n => n.type === 'editorPostChild' && n.data?.postVariant === 'always');
        items.push(
          { key: 'add-post-on-fail', label: '添加 on_fail 子容器', disabled: hasOnFail, onClick: () => handleAddNodeFromContext('post_child_on_fail') },
          { key: 'add-post-on-success', label: '添加 on_success 子容器', disabled: hasOnSuccess, onClick: () => handleAddNodeFromContext('post_child_on_success') },
          { key: 'add-post-always', label: '添加 always 子容器', disabled: hasAlways, onClick: () => handleAddNodeFromContext('post_child_always') },
        );
      }

      // 容器折叠/展开
      if (isContainer) {
        items.push({
          key: 'toggle-collapse',
          label: isCollapsed ? '展开' : '折叠',
          onClick: () => handleToggleCollapse(contextMenu.nodeId!),
        });
      }

      // 通用操作
      items.push(
        { key: 'properties', label: '属性', onClick: () => handleNodeProperties(contextMenu.nodeId!) },
        { key: 'delete', label: '删除', danger: true, onClick: () => handleDeleteNode(contextMenu.nodeId!) },
      );

      return items;
    }

    return [];
  }, [contextMenu, nodes, handleAddNodeFromContext, handleToggleCollapse, handleNodeProperties, handleDeleteNode]);

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
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
      }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* v2 (2026-07): 工具栏 */}
      {!readOnly && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '6px 12px',
            borderBottom: '1px solid #e5e7eb',
            background: '#ffffff',
            flexShrink: 0,
            zIndex: 10,
          }}
        >
          <Tooltip title="保存工作流">
            <button
              onClick={handleSave}
              disabled={!isDirty}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 6,
                background: isDirty ? '#eff6ff' : '#f9fafb',
                color: isDirty ? '#1d4ed8' : '#9ca3af',
                cursor: isDirty ? 'pointer' : 'not-allowed',
                fontSize: 12, fontWeight: 500,
                opacity: isDirty ? 1 : 0.6,
              }}
            >
              <SaveOutlined />
              保存
            </button>
          </Tooltip>
          <Tooltip title="自动布局（dagre）">
            <button
              onClick={handleAutoLayout}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 6,
                background: '#ffffff', color: '#374151',
                cursor: 'pointer', fontSize: 12, fontWeight: 500,
              }}
            >
              <ApartmentOutlined />
              布局
            </button>
          </Tooltip>
          <Tooltip title="适应窗口">
            <button
              onClick={handleFitView}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 6,
                background: '#ffffff', color: '#374151',
                cursor: 'pointer', fontSize: 12, fontWeight: 500,
              }}
            >
              <ExpandOutlined />
              适应
            </button>
          </Tooltip>
          <Tooltip title="导出为图片">
            <button
              onClick={handleExportImage}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '4px 10px', border: '1px solid #d1d5db', borderRadius: 6,
                background: '#ffffff', color: '#374151',
                cursor: 'pointer', fontSize: 12, fontWeight: 500,
              }}
            >
              <CameraOutlined />
              导出
            </button>
          </Tooltip>
          {isDirty && (
            <span style={{ fontSize: 11, color: '#f59e0b', marginLeft: 8 }}>
              有未保存的修改
            </span>
          )}
        </div>
      )}

      {/* 画布区域 */}
      <div style={{ flex: 1, position: 'relative' }}>
        <ReactFlow
          nodes={syncedNodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onInit={(instance) => { reactFlowInstanceRef.current = instance; }}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onNodeClick={handleNodeClick}
          onNodeContextMenu={handleNodeContextMenu}
          onPaneClick={handlePaneClick}
          onPaneContextMenu={handlePaneContextMenu}
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

        {/* v2 (2026-07): 右键菜单（画布内 Dropdown） */}
        {contextMenu && contextMenu.open && (
          <div
            style={{
              position: 'fixed',
              left: contextMenu.x,
              top: contextMenu.y,
              zIndex: 1000,
            }}
          >
            <Dropdown
              menu={{ items: contextMenuItems }}
              open
              onOpenChange={(open) => { if (!open) setContextMenu(null); }}
              trigger={['contextMenu']}
              getPopupContainer={() => document.body}
            >
              {/* 使用一个不可见的div，让Dropdown菜单出现 */}
              <div style={{ width: 0, height: 0 }} />
            </Dropdown>
          </div>
        )}

        {/* v2 (2026-07): 右键菜单 fallback — 使用 antd Dropdown 不可见元素方式不可靠时，用绝对定位的菜单 */}
        {contextMenu && contextMenu.open && (
          <div
            style={{
              position: 'fixed',
              left: contextMenu.x,
              top: contextMenu.y,
              zIndex: 1001,
              background: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
              minWidth: 180,
              padding: '4px 0',
              pointerEvents: 'auto',
            }}
            onClick={handleCloseContextMenu}
          >
            {contextMenuItems?.map((item) => {
              if (!item || 'children' in item) return null;
              const menuItem = item as { key: string; label: string; disabled?: boolean; danger?: boolean; onClick?: () => void };
              return (
                <div
                  key={menuItem.key}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!menuItem.disabled) {
                      menuItem.onClick?.();
                    }
                  }}
                  style={{
                    padding: '6px 16px',
                    fontSize: 13,
                    color: menuItem.disabled ? '#cbd5e1' : menuItem.danger ? '#ef4444' : '#374151',
                    cursor: menuItem.disabled ? 'not-allowed' : 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                  className="hover:bg-gray-100"
                >
                  {menuItem.label}
                </div>
              );
            })}
          </div>
        )}

        {/* 右键菜单覆盖层 — 点击其他地方关闭 */}
        {contextMenu && contextMenu.open && (
          <div
            onClick={handleCloseContextMenu}
            onContextMenu={(e) => { e.preventDefault(); handleCloseContextMenu(); }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 999,
            }}
          />
        )}
      </div>
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
