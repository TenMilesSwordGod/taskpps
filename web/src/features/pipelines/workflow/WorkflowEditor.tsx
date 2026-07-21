import { useCallback, useMemo, useRef, DragEvent, useState, forwardRef, useImperativeHandle } from 'react';
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
import { message, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { SaveOutlined, ApartmentOutlined, ExpandOutlined, CameraOutlined } from '@ant-design/icons';
import EditorTaskNode from './nodes/EditorTaskNode';
import EditorSubPipelineNode from './nodes/EditorSubPipelineNode';
import EditorPostParentNode from './nodes/EditorPostParentNode';
import EditorPostChildNode from './nodes/EditorPostChildNode';
import EditorStartEndNode from './nodes/EditorStartEndNode';
import EditorPipelineNode from './nodes/EditorPipelineNode';
import { ReadOnlyCtx } from './nodes/ReadOnlyContext';
import { yamlToNodes } from './yamlToNodes';
import { INK } from '../nodes/nodeTokens';
import type { EditorNodeData, EditorEdgeData } from './yamlToNodes';
import type { PipelineDetail } from '@/types';
import { applyDagreLayout } from '@/utils/dagreLayout';
import { validateDrop, findDropParentContext, getAbsolutePosition, type DropContext } from './validateDrop';

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

export interface WorkflowEditorRef {
  deleteNode: (nodeId: string) => void;
}

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

const WorkflowEditor = forwardRef<WorkflowEditorRef, WorkflowEditorProps>(function WorkflowEditor({
  pipeline,
  selectedNodeId,
  onNodeSelect,
  onGraphChange,
  readOnly = false,
}, ref) {
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

      // bug #35 关联：连线改变 edges，需同步回传父组件 editEdges，
      // 否则新增连线在保存时丢失。
      const newEdge: Edge<EditorEdgeData> = {
        ...connection,
        type: 'smoothstep',
        markerEnd: { type: 'arrowclosed' as const, width: 8, height: 8, color: '#94a3b8' },
        style: { stroke: '#94a3b8', strokeWidth: 2 },
        data: {
          edgeType: 'explicit',
          explicit: true,
          implicit: false,
        },
      } as Edge<EditorEdgeData>;
      const newEdges = addEdge(newEdge, edges);
      setEdges(newEdges);
      onGraphChange?.(nodes, newEdges);
    },
    [readOnly, setEdges, edges, nodes, onGraphChange],
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
          // 注意(2026-07): 新节点的 position 需相对其直接父容器，而容器自身可能是嵌套节点
          // （position 是相对它自己的父级的）。必须先换算容器的绝对坐标，再用落点绝对坐标相减，
          // 才能得到正确的相对坐标，避免拖入嵌套容器时位置错位。
          const absContainer = getAbsolutePosition(container, nodes);
          nodePosition = {
            x: position.x - absContainer.x,
            y: position.y - absContainer.y,
          };
          nodeParentId = containerParentId;
        }
      }

      // bug #35 关联修复：各分支只负责构造 newNode，最后统一 setNodes + onGraphChange，
      // 避免每处重复回传，也保证新增节点实时同步到父组件 editNodes（否则保存时丢失）。
      let newNode: Node<EditorNodeData> | null = null;

      if (nodeTypeName === 'subpipeline') {
        newNode = {
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
      } else if (nodeTypeName === 'task') {
        newNode = {
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
      } else if (nodeTypeName === 'post_parent') {
        newNode = {
          id: nodeId,
          type: 'editorPostParent',
          position: nodePosition,
          parentId: nodeParentId,
          style: { width: 280, height: 150 },
          data: { label: label || 'Post 处理容器' },
        };
      } else if (nodeTypeName.startsWith('post_child_')) {
        const variantMap: Record<string, 'on_fail' | 'on_success' | 'always'> = {
          post_child_on_fail: 'on_fail',
          post_child_on_success: 'on_success',
          post_child_always: 'always',
        };
        const postVariant = variantMap[nodeTypeName] || 'on_fail';
        newNode = {
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
      } else if (nodeTypeName === 'startend') {
        newNode = {
          id: nodeId,
          type: 'editorStartEnd',
          position: nodePosition,
          parentId: nodeParentId,
          data: { variant: 'start' },
        };
      } else if (nodeTypeName.startsWith('task_atomic_')) {
        const typeMap: Record<string, 'command' | 'steps' | 'plugin' | 'invoke'> = {
          task_atomic_cmd: 'command',
          task_atomic_step: 'steps',
          task_atomic_plugin: 'plugin',
          task_atomic_invoke: 'invoke',
        };
        const taskType = typeMap[nodeTypeName] || 'command';
        const taskData = { name: label || '新任务', env: {}, retry: 0, depends_on: [] };
        // bug #50 (2026-07): 原子行为拖入 Post 容器时，创建 editorPostChild 节点而非 editorTask
        if (parentContext === 'post_parent') {
          newNode = {
            id: nodeId,
            type: 'editorPostChild',
            position: nodePosition,
            parentId: nodeParentId,
            data: {
              task: taskData,
              taskType,
              postVariant: 'on_fail',
            },
          };
        } else {
          newNode = {
            id: nodeId,
            type: 'editorTask',
            position: nodePosition,
            parentId: nodeParentId,
            data: {
              task: taskData,
              taskType,
              subpipelineName: '',
            },
          };
        }
      }

      if (newNode) {
        const newNodes = [...nodes, newNode];
        setNodes(newNodes);
        onGraphChange?.(newNodes, edges);
        setIsDirty(true);
      }

      message.success(`已添加节点: ${label || nodeTypeName}`);
    },
    [setNodes, nodes, edges, onGraphChange],
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
      // 关键修复（bug #35）：直接基于当前 nodes/edges 计算删除后的新图并回传父组件。
      // 原实现只更新内部 state 而未调用 onGraphChange，导致父组件的 editNodes
      // 未同步删除，PropertyPanel 删除节点后保存时该节点"复活"。
      // 这里用闭包里的 nodes/edges 显式计算新数组，避免 setState 回调异步导致回传旧值。
      const newNodes = nodes.filter((n) => n.id !== nodeId);
      const newEdges = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
      setNodes(newNodes);
      setEdges(newEdges);
      onGraphChange?.(newNodes, newEdges);
      if (selectedNodeId === nodeId) {
        onNodeSelect(null);
      }
      setIsDirty(true);
      message.success('节点已删除');
      setContextMenu(null);
    },
    [setNodes, setEdges, selectedNodeId, onNodeSelect, onGraphChange, nodes, edges],
  );

  // v4 (2026-07): 键盘 Delete/Backspace 删除选中节点
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedNodeId) {
        const node = nodes.find(n => n.id === selectedNodeId);
        // 不允许删除哨兵节点（Start/End/Pipeline）
        if (node && !['__start__', '__end__', '__pipeline__'].includes(node.id)) {
          event.preventDefault();
          handleDeleteNode(selectedNodeId);
        }
      }
    },
    [selectedNodeId, nodes, handleDeleteNode],
  );

  // 折叠/展开节点
  const handleToggleCollapse = useCallback(
    (nodeId: string) => {
      // bug #35 关联：折叠虽不影响 YAML（不标 dirty），但仍应回传新图，
      // 保证父组件 editNodes 与画布一致，避免后续保存基于过期数据。
      const newNodes = nodes.map((n) => {
        if (n.id !== nodeId) return n;
        const collapsed = !n.data?.collapsed;
        return {
          ...n,
          data: { ...n.data, collapsed },
          style: collapsed
            ? { ...(n.style as object), width: 140, height: 48 }
            : n.style,
        };
      });
      setNodes(newNodes);
      onGraphChange?.(newNodes, edges);
      setIsDirty(false); // 折叠不影响 YAML，不标 dirty
      setContextMenu(null);
    },
    [setNodes, nodes, edges, onGraphChange],
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
  // v6 (2026-07 / bug #41): 改为从 contextMenu 状态读取右键目标节点信息，
  // 替代原 postParentId 参数方式。原因是原设计只考虑了 PostParent 一种容器，
  // postParentId 参数仅能传递"是否 PostParent"的区分，SubPipeline 右键时该参数
  // 为 undefined 导致新增节点始终落入画布根级（parentId=undefined, position=(200,200)）。
  // 现在通过 contextMenu.nodeType 区分三种上下文（subpipeline / post_parent / canvas-root），
  // 再根据上下文设置 parentId 与相对坐标，与 handleDrop 和 findDropParentContext 的
  // 策略对齐。
  const handleAddNodeFromContext = useCallback(
    (nodeTypeName: string) => {
      // 从当前右键上下文确定父容器类型和 parentId
      let parentContext: DropContext = 'canvas-root';
      let containerParentId: string | undefined;

      if (contextMenu?.nodeId && contextMenu?.nodeType) {
        if (contextMenu.nodeType === 'editorSubPipeline') {
          parentContext = 'subpipeline';
          containerParentId = contextMenu.nodeId;
        } else if (contextMenu.nodeType === 'editorPostParent') {
          parentContext = 'post_parent';
          containerParentId = contextMenu.nodeId;
        } else if (contextMenu.nodeType === 'editorPipeline') {
          // v7 (2026-07): Pipeline 根容器上右键添加 SubPipeline → 归入根容器内
          // parentContext='canvas-root' 让 validateDrop 放行（R1 只拦截 subpipeline-in-subpipeline），
          // containerParentId='__pipeline__' 使新 SubPipeline 正确嵌入根容器。
          parentContext = 'canvas-root';
          containerParentId = '__pipeline__';
        }
      }

      const validationError = validateDrop(nodeTypeName, parentContext, nodes);
      if (validationError) {
        message.error(validationError);
        setContextMenu(null);
        return;
      }

      const nodeId = `__new__${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;

      // v6 (2026-07 / bug #41): 容器内用相对坐标（使节点落在父容器可视区域内），
      // 画布根级沿用原有默认位置，保证不破坏 canvas-root 分支。
      // 注意(2026-07): 不引入 screenToFlowPosition（右键菜单无拖拽落点，坐标不可靠），
      // 直接用简单偏移确保节点出现在父容器内合理位置。
      let position = { x: 200, y: 200 };
      if (containerParentId) {
        position = { x: 20, y: 40 };
      }

      // bug #35 关联：统一构造 newNode 后 setNodes + onGraphChange，
      // 保证右键新增节点实时同步父组件 editNodes，避免保存时丢失。
      let newNode: Node<EditorNodeData> | null = null;
      if (nodeTypeName === 'subpipeline') {
        newNode = {
          id: nodeId, type: 'editorSubPipeline', position,
          style: { width: 260, height: 140 },
          parentId: containerParentId,
          data: { label: '新 SubPipeline', executionStrategy: 'sequential' },
        };
      } else if (nodeTypeName === 'task') {
        newNode = {
          id: nodeId, type: 'editorTask', position,
          parentId: containerParentId,
          data: { task: { name: '新 Task', env: {}, retry: 0, depends_on: [] }, taskType: 'command', subpipelineName: '' },
        };
      } else if (nodeTypeName === 'post_parent') {
        newNode = {
          id: nodeId, type: 'editorPostParent', position,
          style: { width: 280, height: 150 },
          parentId: containerParentId,
          data: { label: 'Post 处理容器' },
        };
      } else if (nodeTypeName === 'startend') {
        newNode = {
          id: nodeId, type: 'editorStartEnd', position,
          parentId: containerParentId,
          data: { variant: 'start' },
        };
      } else if (nodeTypeName.startsWith('post_child_')) {
        // bug #37: 新增对 post_child_* 类型的处理（原实现无此分支，newNode 恒为 null，点击无效）。
        // 构造 editorPostChild 节点，postVariant 由类型前缀映射，parentId 指向右键的 Post 父容器，
        // 使节点真正落入该父容器内部（nodesToYaml 按 parentId 分组，能正确序列化回 YAML）。
        const variantMap: Record<string, 'on_fail' | 'on_success' | 'always'> = {
          post_child_on_fail: 'on_fail',
          post_child_on_success: 'on_success',
          post_child_always: 'always',
        };
        const postVariant = variantMap[nodeTypeName] || 'on_fail';
        // 复用 yamlToNodes 的命名约定：`__postchild__<parentId>_<variant>_<idx>`，
        // 既保证 id 稳定可定位，也保证与初始反序列化生成的子节点 id 完全同构，便于后续双向同步。
        const siblingCount = nodes.filter(
          (n) => n.type === 'editorPostChild' && n.parentId === containerParentId && n.data?.postVariant === postVariant,
        ).length;
        const childId = `__postchild__${containerParentId}_${postVariant}_${siblingCount}`;
        // Post 父容器内相对坐标：沿用 yamlToNodes 的容器内边距与纵向排列，确保子节点落在父容器内。
        newNode = {
          id: childId,
          type: 'editorPostChild',
          position: { x: 40, y: 40 + siblingCount * 80 },
          parentId: containerParentId,
          data: {
            task: { name: '新 Post Task', env: {}, retry: 0, depends_on: [] },
            taskType: 'command',
            postVariant,
          },
        };
      }

      if (newNode) {
        const newNodes = [...nodes, newNode];
        setNodes(newNodes);
        onGraphChange?.(newNodes, edges);
        setIsDirty(true);
      }
      message.success(`已添加节点: ${nodeTypeName}`);
      setContextMenu(null);
    },
    [setNodes, nodes, edges, onGraphChange, contextMenu],
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
      // v5 (2026-07 / bug #46): 将子节点 position 从绝对坐标转为相对父容器的偏移
      // 根因：dagre 给所有节点输出 canvas 级别的绝对坐标，但 ReactFlow 对有 parentId
      // 的子节点将 position 解释为相对父容器的偏移。若不转换，子节点会以绝对坐标+
      // 父容器偏移叠加渲染，导致节点"到处乱飞"。
      // 这里的转换逻辑与 usePipelineGraph.ts:648-663 保持一致。
      const layoutedMap = new Map(layouted.map((n) => [n.id, n]));
      const adjusted = layouted.map((node) => {
        if (node.parentId) {
          const parent = layoutedMap.get(node.parentId);
          if (parent) {
            return {
              ...node,
              position: {
                x: (node.position.x as number) - (parent.position.x as number),
                y: (node.position.y as number) - (parent.position.y as number),
              },
            };
          }
        }
        return { ...node };
      });
      setNodes(adjusted as unknown as Node<EditorNodeData>[]);
      onGraphChange?.(adjusted as unknown as Node<EditorNodeData>[], edges);
      setIsDirty(true);
      message.success('自动布局完成');
    } catch {
      message.error('自动布局失败');
    }
  }, [nodes, edges, setNodes, onGraphChange]);

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
      // v6 (2026-07 / bug #41): 不传 parentId，由 handleAddNodeFromContext 从 contextMenu 自行读取。
      if (node?.type === 'editorSubPipeline') {
        items.push({ key: 'add-task-inside', label: '添加 Task', onClick: () => handleAddNodeFromContext('task') });
      }

      // v7 (2026-07): Pipeline 根容器右键 — 添加 SubPipeline（自动归入 __pipeline__ 内）
      if (node?.type === 'editorPipeline') {
        items.push({ key: 'add-subpipeline-inside', label: '添加 SubPipeline', onClick: () => handleAddNodeFromContext('subpipeline') });
      }

      // Post 父容器内部右键 — 添加 Post 子容器
      if (node?.type === 'editorPostParent') {
        const hasOnFail = nodes.some(n => n.type === 'editorPostChild' && n.data?.postVariant === 'on_fail');
        const hasOnSuccess = nodes.some(n => n.type === 'editorPostChild' && n.data?.postVariant === 'on_success');
        const hasAlways = nodes.some(n => n.type === 'editorPostChild' && n.data?.postVariant === 'always');
        // v6 (2026-07 / bug #41): 不再传 contextMenu.nodeId!，父容器 id 由 handleAddNodeFromContext 从 contextMenu 状态自动读取。
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

  // v4 (2026-07): 暴露 handleDeleteNode 给父组件（PropertyPanel 删除路径）
  useImperativeHandle(ref, () => ({
    deleteNode: (nodeId: string) => handleDeleteNode(nodeId),
  }), [handleDeleteNode]);

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
      tabIndex={0}
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: INK.canvas,
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        outline: 'none',
      }}
      onKeyDown={handleKeyDown}
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
        <ReadOnlyCtx.Provider value={readOnly}>
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
          isValidConnection={isValidConnection}
        >
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
            nodeColor={miniMapColor}
            nodeStrokeColor="#fff"
            maskColor="rgba(241, 245, 249, 0.6)"
            className="!shadow-sm !border !border-slate-200 !rounded !overflow-hidden"
            position="bottom-left"
            zoomable
            pannable
          />
        </ReactFlow>

        </ReadOnlyCtx.Provider>

        {/* 注意(2026-07): 右键菜单仅保留自定义绝对定位 div 一份，移除冗余的 antd <Dropdown> 块。
            原因：原先同时存在 antd Dropdown（zIndex 1000）与自定义 div（zIndex 1001）两套菜单，
            右键时内容重复渲染（同一菜单项出现两次）并引发 zIndex 冲突/闪烁。自定义 div 已通过
            contextMenuItems 完整渲染"添加 SubPipeline"/属性/删除等项且 onClick 处理完善，
            因此直接删除 antd Dropdown，避免双重渲染。 */}
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
});

// v4 (2026-07 / Bug#45): 连接校验函数
// 只要 source 端是 out/post 类 handle 且 target 端是 in 类 handle 即允许，
// 确保不会出现 target→target 或 source→source 等无效连接
export function isValidConnection(
  connection: { source: string; target: string; sourceHandle: string | null; targetHandle: string | null },
): boolean {
  const { sourceHandle, targetHandle } = connection;
  if (!sourceHandle || !targetHandle) return false;

  const sourceIsOutput = sourceHandle === 'out' || sourceHandle === 'post';
  const targetIsInput = targetHandle === 'in';

  return sourceIsOutput && targetIsInput;
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

export default WorkflowEditor;
