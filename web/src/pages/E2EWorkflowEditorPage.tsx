import { useState, useCallback } from 'react';
import WorkflowEditor from '@/features/pipelines/workflow/WorkflowEditor';
import NodePalette from '@/features/pipelines/workflow/NodePalette';
import PropertyPanel from '@/features/pipelines/workflow/PropertyPanel';
import type { PipelineDetail } from '@/types';
import type { EditorNodeData, EditorEdgeData } from '@/features/pipelines/workflow/yamlToNodes';
import type { Node, Edge } from '@xyflow/react';

/**
 * e2e 测试专用页面 — 绕过认证和 API 依赖，独立渲染 WorkflowEditor。
 *
 * 设计决策（为什么这么写）：
 * - 生产路由需要 RequireAuth + API 后端，Playwright 在 CI/无后端环境下无法直接访问。
 *   此页面加载纯前端 mock 数据渲染 WorkflowEditor，覆盖 jsdom 无法测试的交互场景。
 * - 放在 /pages/ 目录而非 /e2e/ 目录，与现有 LoginPage 等页面同级，
 *   避免 Vite dev server 的静态资源服务路径问题。
 * - Python 参数拼接确保确定性节点 ID，避免 UUID 导致测试选择器不稳定。
 */

/** 构建包含 SubPipeline + Task + Post 的 mock pipeline，用于测试完整交互 */
function makeMockPipeline(): PipelineDetail {
  return {
    name: 'e2e-test-pipeline',
    tasks: [
      { name: 'init', env: {}, retry: 0, depends_on: [] },
      { name: 'cleanup', env: {}, retry: 0, depends_on: ['init'] },
    ],
    pipelines: [
      {
        name: 'build',
        config: { env: {}, retry: 0, on_failure: '', execution_strategy: 'sequential' },
        depends_on: [],
        tasks: [
          { name: 'compile', env: {}, retry: 1, depends_on: [] },
          { name: 'lint', env: {}, retry: 0, depends_on: ['compile'] },
        ],
      },
    ],
    post: {
      on_fail: [
        { name: 'notify_fail', env: {}, retry: 0, depends_on: [] },
      ],
    },
  };
}

export default function E2EWorkflowEditorPage() {
  const [pipeline] = useState<PipelineDetail>(makeMockPipeline);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [editNodes, setEditNodes] = useState<Node<EditorNodeData>[]>([]);
  const [editEdges, setEditEdges] = useState<Edge<EditorEdgeData>[]>([]);
  const [propertyPanelVisible, setPropertyPanelVisible] = useState(false);
  const [editingNode, setEditingNode] = useState<Node<EditorNodeData> | null>(null);

  const handleEditorNodeSelect = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      const node = editNodes.find((n) => n.id === nodeId);
      if (node) {
        setEditingNode(node);
        setPropertyPanelVisible(true);
      }
    } else {
      setPropertyPanelVisible(false);
      setEditingNode(null);
    }
  }, [editNodes]);

  const handleGraphChange = useCallback(
    (nodes: Node<EditorNodeData>[], edges: Edge<EditorEdgeData>[]) => {
      setEditNodes(nodes);
      setEditEdges(edges);
    },
    [],
  );

  const handlePropertySave = useCallback((updatedNode: Node<EditorNodeData>) => {
    setEditNodes((prev) => prev.map((n) => (n.id === updatedNode.id ? updatedNode : n)));
  }, []);

  const handlePropertyDelete = useCallback((nodeId: string) => {
    setEditNodes((prev) => prev.filter((n) => n.id !== nodeId));
    setEditEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId));
  }, []);

  return (
    <div
      data-testid="e2e-workflow-editor-root"
      style={{ width: '100vw', height: '100vh', display: 'flex' }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <WorkflowEditor
          pipeline={pipeline}
          selectedNodeId={selectedNodeId}
          onNodeSelect={handleEditorNodeSelect}
          onGraphChange={handleGraphChange}
        />
      </div>
      <NodePalette />
      <PropertyPanel
        selectedNode={editingNode}
        visible={propertyPanelVisible}
        onClose={() => {
          setPropertyPanelVisible(false);
          setEditingNode(null);
        }}
        onSave={handlePropertySave}
        onDelete={handlePropertyDelete}
      />
    </div>
  );
}
