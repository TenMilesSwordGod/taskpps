import { useState, useCallback, useRef } from 'react';
import { message } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import WorkflowEditor, { type WorkflowEditorRef } from '@/features/pipelines/workflow/WorkflowEditor';
import NodePalette from '@/features/pipelines/workflow/NodePalette';
import PropertyPanel from '@/features/pipelines/workflow/PropertyPanel';
import type { PipelineDetail } from '@/types';
import type { EditorNodeData } from '@/features/pipelines/workflow/yamlToNodes';
import type { Node } from '@xyflow/react';

/**
 * e2e 测试专用页面 — 绕过认证和 API 依赖，独立渲染 WorkflowEditor。
 *
 * 设计决策（为什么这么写）：
 * - 生产路由需要 RequireAuth + API 后端，Playwright 在 CI/无后端环境下无法直接访问。
 *   此页面加载纯前端 mock 数据渲染 WorkflowEditor，覆盖 jsdom 无法测试的交互场景。
 * - 放在 /pages/ 目录而非 /e2e/ 目录，与现有 LoginPage 等页面同级，
 *   避免 Vite dev server 的静态资源服务路径问题。
 * - Python 参数拼接确保确定性节点 ID，避免 UUID 导致测试选择器不稳定。
 *
 * v2 (2026-07): 补充"保存"按钮（dirty 状态驱动 disabled）与属性面板同步 ——
 *   原先 v3 移除了 WorkflowEditor 内部保存按钮后此页无保存入口，e2e 断言失败；
 *   属性面板保存/删除也只改父组件状态，画布不更新。
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
  const [propertyPanelVisible, setPropertyPanelVisible] = useState(false);
  const [editingNode, setEditingNode] = useState<Node<EditorNodeData> | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const editorRef = useRef<WorkflowEditorRef>(null);

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

  // v2: 页面只需同步 nodes（本页保存不序列化 edges）
  const handleGraphChange = useCallback((nodes: Node<EditorNodeData>[]) => {
    setEditNodes(nodes);
  }, []);

  const handlePropertySave = useCallback((updatedNode: Node<EditorNodeData>) => {
    // v2: 同步画布内部状态，否则属性面板改名后画布节点文字不变
    editorRef.current?.updateNode(updatedNode);
    setEditNodes((prev) => prev.map((n) => (n.id === updatedNode.id ? updatedNode : n)));
  }, []);

  const handlePropertyDelete = useCallback((nodeId: string) => {
    editorRef.current?.deleteNode(nodeId);
    setEditNodes((prev) => prev.filter((n) => n.id !== nodeId));
  }, []);

  const handleSave = useCallback(() => {
    // 保存成功后清除 dirty，保存按钮回到 disabled
    editorRef.current?.markClean();
    message.success('工作流已保存');
  }, []);

  return (
    <div
      data-testid="e2e-workflow-editor-root"
      style={{ width: '100vw', height: '100vh', display: 'flex' }}
    >
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* v2: 保存按钮条（dirty 状态驱动 disabled） */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 12px',
            borderBottom: '1px solid #e5e7eb',
            background: '#ffffff',
            flexShrink: 0,
          }}
        >
          <button
            onClick={handleSave}
            disabled={!editorDirty}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '4px 12px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              background: editorDirty ? '#1677ff' : '#f3f4f6',
              color: editorDirty ? '#ffffff' : '#9ca3af',
              cursor: editorDirty ? 'pointer' : 'not-allowed',
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            <SaveOutlined />
            保存
          </button>
          {editorDirty && (
            <span style={{ fontSize: 11, color: '#f59e0b' }}>有未保存的修改</span>
          )}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <WorkflowEditor
            ref={editorRef}
            pipeline={pipeline}
            selectedNodeId={selectedNodeId}
            onNodeSelect={handleEditorNodeSelect}
            onGraphChange={handleGraphChange}
            onDirtyChange={setEditorDirty}
          />
        </div>
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
