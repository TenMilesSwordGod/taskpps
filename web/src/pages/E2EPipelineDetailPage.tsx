import { useState, useRef, useCallback, useMemo } from 'react';
import { Button, Space, Tooltip, message, Alert } from 'antd';
import { EditOutlined, EyeOutlined, SaveOutlined, CodeOutlined, CloseOutlined } from '@ant-design/icons';
import PipelineGraph from '@/features/pipelines/PipelineGraph';
import YamlEditor from '@/features/pipelines/YamlEditor';
import type { YamlEditorRef } from '@/features/pipelines/YamlEditor';
import WorkflowEditor from '@/features/pipelines/workflow/WorkflowEditor';
import NodePalette from '@/features/pipelines/workflow/NodePalette';
import PropertyPanel from '@/features/pipelines/workflow/PropertyPanel';
import { nodesToYaml } from '@/features/pipelines/workflow/nodesToYaml';
import { parseYamlToPipeline, pipelineToYaml } from '@/utils/yamlParser';
import type { PipelineDetail, ValidationError } from '@/types';
import type { EditorNodeData, EditorEdgeData } from '@/features/pipelines/workflow/yamlToNodes';
import type { Node, Edge } from '@xyflow/react';

/**
 * e2e 测试专用页面 — PipelineDetailPage 集成测试。
 *
 * 设计决策（为什么这么写）：
 * - 生产路由 /pipelines/:projectId/:definitionId 在 RequireAuth 守卫内，
 *   且依赖 usePipelineById API。Playwright 在 CI/无后端环境下无法直接访问。
 * - 此页面加载 mock pipeline 数据，独立渲染 PipelineDetailPage 的核心结构：
 *   编辑/查看模式切换、WorkflowEditor、NodePalette、PropertyPanel、PipelineGraph、
 *   YamlEditor、保存功能。
 * - 与 E2EWorkflowEditorPage 使用相同的 mock pipeline 结构，保证一致性。
 */

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

export default function E2EPipelineDetailPage() {
  const [pipeline] = useState<PipelineDetail>(makeMockPipeline);

  const [editMode, setEditMode] = useState(false);
  const [editNodes, setEditNodes] = useState<Node<EditorNodeData>[]>([]);
  const [editEdges, setEditEdges] = useState<Edge<EditorEdgeData>[]>([]);
  const [propertyPanelVisible, setPropertyPanelVisible] = useState(false);
  const [editingNode, setEditingNode] = useState<Node<EditorNodeData> | null>(null);

  const [yamlEditorOpen, setYamlEditorOpen] = useState(false);
  const [yamlText, setYamlText] = useState('');
  const [yamlError, setYamlError] = useState<ValidationError | null>(null);
  const [editedPipeline, setEditedPipeline] = useState<PipelineDetail | null>(null);
  const yamlEditorRef = useRef<YamlEditorRef>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);

  // 保存：nodes/edges → YAML → 模拟写回（不调真实 API）
  const handleSaveFromEditor = useCallback(() => {
    const { pipeline: result, errors } = nodesToYaml(editNodes, editEdges);
    if (!result) {
      message.error(`保存失败: ${errors.join(', ')}`);
      return;
    }
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      message.success('已保存');
    }, 300);
  }, [editNodes, editEdges]);

  // 编辑器节点选择
  const handleEditorNodeSelect = useCallback((nodeId: string | null) => {
    setSelectedTaskId(nodeId);
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

  // 编辑器节点属性保存
  const handlePropertySave = useCallback((updatedNode: Node<EditorNodeData>) => {
    setEditNodes((prev) => prev.map((n) => (n.id === updatedNode.id ? updatedNode : n)));
  }, []);

  // 编辑器节点删除
  const handlePropertyDelete = useCallback((nodeId: string) => {
    setEditNodes((prev) => prev.filter((n) => n.id !== nodeId));
    setEditEdges((prev) => prev.filter((e) => e.source !== nodeId && e.target !== nodeId));
  }, []);

  // graph 变化回调
  const handleGraphChange = useCallback((nodes: Node<EditorNodeData>[], edges: Edge<EditorEdgeData>[]) => {
    setEditNodes(nodes);
    setEditEdges(edges);
  }, []);

  // 打开 YAML 编辑器时用当前 pipeline 生成 YAML
  const handleToggleEditor = useCallback(() => {
    if (!yamlEditorOpen) {
      const yaml = pipelineToYaml(pipeline);
      setYamlText(yaml);
      setEditedPipeline(null);
      setYamlError(null);
    }
    setYamlEditorOpen((prev) => !prev);
  }, [yamlEditorOpen, pipeline]);

  // YAML 内容变化时解析并更新流程图
  const handleYamlChange = useCallback((text: string) => {
    setYamlText(text);
    const result = parseYamlToPipeline(text);
    if (result.success) {
      setEditedPipeline(result.pipeline!);
      setYamlError(null);
    } else {
      setYamlError(result.error!);
    }
  }, []);

  // 点击 DAG 节点 → YAML 编辑器滚动到对应行 + 高亮节点
  const handleNodeClick = useCallback((taskId: string) => {
    setSelectedTaskId(taskId || null);
    if (!yamlEditorOpen || !taskId) return;
    const taskName = taskId.includes('.') ? taskId.split('.').pop()! : taskId;
    const escaped = taskName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const lines = yamlText.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].match(new RegExp(`-\\s+name:\\s+${escaped}\\b`))) {
        yamlEditorRef.current?.scrollToLine(i + 1);
        return;
      }
    }
  }, [yamlEditorOpen, yamlText]);

  // 显示的 pipeline：编辑器打开时用编辑后的版本，否则用原始版本
  const displayPipeline: PipelineDetail | undefined = useMemo(() => {
    if (yamlEditorOpen && editedPipeline) return editedPipeline;
    return pipeline;
  }, [yamlEditorOpen, editedPipeline, pipeline]);

  // YAML 光标所在行 → taskName 映射
  const taskNameToNodeId = useMemo(() => {
    const map = new Map<string, string>();
    const p = displayPipeline;
    if (!p) return map;
    p.pipelines?.forEach((sub) => {
      sub.tasks?.forEach((t) => {
        map.set(t.name, `${sub.name}.${t.name}`);
      });
    });
    p.tasks?.forEach((t) => {
      map.set(t.name, t.name);
    });
    return map;
  }, [displayPipeline]);

  const handleCursorTaskChange = useCallback((taskName: string | null) => {
    if (!taskName) {
      setSelectedTaskId(null);
      return;
    }
    const nodeId = taskNameToNodeId.get(taskName) ?? taskName;
    setSelectedTaskId(nodeId);
  }, [taskNameToNodeId]);

  // 保存 YAML（模拟，不调真实 API）
  const handleSaveYaml = useCallback(() => {
    if (!yamlText) return;
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      message.success('已保存');
    }, 300);
  }, [yamlText]);

  return (
    <div data-testid="e2e-pipeline-detail-root" style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* 工具栏 */}
      <div
        data-testid="e2e-toolbar"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 16px',
          borderBottom: '1px solid #e5e7eb',
          backgroundColor: '#f9fafb',
          flexShrink: 0,
        }}
      >
        <Space>
          <Tooltip title={editMode ? '退出编辑模式' : '进入编辑模式'}>
            <Button
              icon={editMode ? <EyeOutlined /> : <EditOutlined />}
              onClick={() => setEditMode((prev) => !prev)}
              type={editMode ? 'primary' : 'default'}
            >
              {editMode ? '查看模式' : '编辑模式'}
            </Button>
          </Tooltip>
          {editMode && (
            <Tooltip title="保存 (Ctrl+S)">
              <Button
                icon={<SaveOutlined />}
                onClick={handleSaveFromEditor}
                loading={saving}
                type="primary"
              >
                保存
              </Button>
            </Tooltip>
          )}
          {!editMode && (
            <Tooltip title={yamlEditorOpen ? '关闭 YAML 编辑器' : '打开 YAML 编辑器'}>
              <Button
                icon={yamlEditorOpen ? <CloseOutlined /> : <CodeOutlined />}
                onClick={handleToggleEditor}
                type={yamlEditorOpen ? 'primary' : 'default'}
              >
                {yamlEditorOpen ? '关闭编辑器' : 'YAML 编辑器'}
              </Button>
            </Tooltip>
          )}
        </Space>
      </div>

      {/* 主内容区 */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        {/* YAML 编辑器面板 — 仅查看模式 */}
        {!editMode && yamlEditorOpen && (
          <div style={{ flexShrink: 0, borderRight: '1px solid #e5e7eb', backgroundColor: '#1e1e1e', width: '40%', minWidth: 300 }}>
            <YamlEditor
              ref={yamlEditorRef}
              value={yamlText}
              onChange={handleYamlChange}
              error={yamlError}
              onCursorTaskChange={handleCursorTaskChange}
              onSave={handleSaveYaml}
              saving={saving}
            />
          </div>
        )}

        {/* DAG 画布 — 仅查看模式 */}
        {!editMode && (
          <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {yamlEditorOpen && yamlError && (
              <Alert
                type="error"
                showIcon
                banner
                message="当前 YAML 非法，画布展示的是上一次有效版本"
                description={
                  <span style={{ fontSize: 12 }}>
                    {yamlError.path ? `${yamlError.path}: ` : ''}
                    {yamlError.line != null ? `行 ${yamlError.line}` : ''}
                    {yamlError.column != null ? `:${yamlError.column} ` : ' '}
                    — {yamlError.message}
                  </span>
                }
                style={{ margin: 0, flexShrink: 0 }}
                closable
              />
            )}
            <div style={{ flex: 1, minHeight: 0 }}>
              <PipelineGraph pipeline={displayPipeline} onNodeClick={handleNodeClick} selectedTaskId={selectedTaskId} />
            </div>
          </div>
        )}

        {/* 编辑模式 — 可编辑画布 + 右侧节点面板 */}
        {editMode && (
          <>
            <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
              <WorkflowEditor
                pipeline={pipeline}
                selectedNodeId={selectedTaskId}
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
          </>
        )}
      </div>
    </div>
  );
}
