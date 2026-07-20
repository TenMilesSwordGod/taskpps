import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Tooltip, message, Spin, Alert } from 'antd';
import {
  ExportOutlined,
  FileImageOutlined,
  CopyOutlined,
  PlayCircleOutlined,
  CodeOutlined,
  CloseOutlined,
  EditOutlined,
  EyeOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import { usePipelineById, usePipelineByFile, useSavePipelineById, useSavePipelineByFile } from '@/api/pipelines';
import PipelineGraph from './PipelineGraph';
import YamlEditor from './YamlEditor';
import type { YamlEditorRef } from './YamlEditor';
import { HelpPanel } from './HelpPanel';
import TriggerRunModal from '@/components/TriggerRunModal';
import PipelineBreadcrumb from '@/components/PipelineBreadcrumb';
import { exportAsPng, exportAsSvg, copyToClipboard } from '@/utils/exportImage';
import { useAppStore } from '@/stores/appStore';
import { parseYamlToPipeline, pipelineToYaml } from '@/utils/yamlParser';
import type { PipelineDetail, ValidationError } from '@/types';
import WorkflowEditor, { type WorkflowEditorRef } from './workflow/WorkflowEditor';
import NodePalette from './workflow/NodePalette';
import PropertyPanel from './workflow/PropertyPanel';
import { nodesToYaml } from './workflow/nodesToYaml';
import type { EditorNodeData, EditorEdgeData } from './workflow/yamlToNodes';
import type { Node, Edge } from '@xyflow/react';

// v2 (2026-07): issue #195 补充 — 非法 pipeline 无 definition_id
// 通过 _file_/* 路由参数获取文件路径，从文件系统加载原始 YAML
// 画布区域显示错误 banner，编辑器展示原始 YAML 供用户修改

/** 流水线详情页 */
export default function PipelineDetailPage() {
  const { projectId, definitionId } = useParams<{ projectId: string; definitionId: string }>();
  // React Router v6 splat param：_file_/* 路由的剩余路径
  const splat = useParams<{ '*': string }>()['*'];
  const navigate = useNavigate();

  // 判断是否为文件路径模式：当 URL 匹配 /pipelines/:projectId/_file_/* 时
  const filePath = splat ? decodeURIComponent(splat) : (definitionId && definitionId !== '_file_' ? undefined : undefined);
  // 额外检测：如果 definitionId 看起来是文件路径（含 .yaml/.yml）且 route 无 splat 时，也用文件模式
  const isFileMode = !!(splat || (definitionId && !definitionId.match(/^[0-9a-fA-F]{8,}$/) && (definitionId.endsWith('.yaml') || definitionId.endsWith('.yml'))));
  const actualFilePath = splat ? decodeURIComponent(splat) : (isFileMode && definitionId ? definitionId : undefined);

  // 正常模式：通过 definition_id 加载
  const { data: pipeline, isLoading: pipelineLoading } = usePipelineById(
    !isFileMode ? definitionId : undefined, projectId
  );
  // 文件模式：通过文件路径加载原始 YAML
  const { data: fileData, isLoading: fileLoading } = usePipelineByFile(
    isFileMode ? projectId : undefined,
    isFileMode ? actualFilePath : undefined,
  );

  const graphWrapperRef = useRef<HTMLDivElement>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const helpPanelMinimized = useAppStore((s) => s.helpPanelMinimized);
  const toggleHelpPanel = useAppStore((s) => s.toggleHelpPanel);

  // YAML 编辑器状态
  const [yamlEditorOpen, setYamlEditorOpen] = useState(isFileMode);
  const [yamlText, setYamlText] = useState('');
  const [yamlError, setYamlError] = useState<ValidationError | null>(null);
  const [editedPipeline, setEditedPipeline] = useState<PipelineDetail | null>(null);
  const yamlEditorRef = useRef<YamlEditorRef>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  // v1 (2026-07): issue #206 — 可视化编辑器模式
  const [editMode, setEditMode] = useState(false);
  const [editNodes, setEditNodes] = useState<Node<EditorNodeData>[]>([]);
  const [editEdges, setEditEdges] = useState<Edge<EditorEdgeData>[]>([]);
  const [propertyPanelVisible, setPropertyPanelVisible] = useState(false);
  const [editingNode, setEditingNode] = useState<Node<EditorNodeData> | null>(null);
  const workflowEditorRef = useRef<WorkflowEditorRef>(null);

  // 保存：正常模式用 by-id，文件模式用 by-file
  const saveByIdMutation = useSavePipelineById(!isFileMode ? definitionId : undefined);
  const saveByFileMutation = useSavePipelineByFile(isFileMode ? projectId : undefined);

  const handleSave = useCallback(() => {
    if (!yamlText) return;
    if (isFileMode && actualFilePath) {
      saveByFileMutation.mutate({ file: actualFilePath, content: yamlText }, {
        onSuccess: () => message.success('已保存'),
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    } else if (definitionId) {
      saveByIdMutation.mutate(yamlText, {
        onSuccess: () => message.success('已保存'),
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    }
  }, [yamlText, isFileMode, actualFilePath, definitionId, saveByFileMutation, saveByIdMutation]);

  const saving = isFileMode ? saveByFileMutation.isPending : saveByIdMutation.isPending;

  // v1 (2026-07): issue #206 — 编辑器中保存：nodes/edges → YAML → 写回
  const handleSaveFromEditor = useCallback(() => {
    const { pipeline: editedPipeline, errors } = nodesToYaml(editNodes, editEdges);
    if (!editedPipeline) {
      message.error(`保存失败: ${errors.join(', ')}`);
      return;
    }
    const yaml = pipelineToYaml(editedPipeline);
    if (isFileMode && actualFilePath) {
      saveByFileMutation.mutate({ file: actualFilePath, content: yaml }, {
        onSuccess: () => message.success('已保存'),
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    } else if (definitionId) {
      saveByIdMutation.mutate(yaml, {
        onSuccess: () => message.success('已保存'),
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    }
  }, [editNodes, editEdges, isFileMode, actualFilePath, definitionId, saveByFileMutation, saveByIdMutation]);

  // 编辑器节点选择处理
  const handleEditorNodeSelect = useCallback((nodeId: string | null) => {
    setSelectedTaskId(nodeId);
    if (nodeId) {
      const node = editNodes.find(n => n.id === nodeId);
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
    setEditNodes(prev => prev.map(n => n.id === updatedNode.id ? updatedNode : n));
  }, []);

  // 编辑器节点删除
  // v4 (2026-07): 委托给 WorkflowEditor 的 handleDeleteNode（单数据源）
  const handlePropertyDelete = useCallback((nodeId: string) => {
    workflowEditorRef.current?.deleteNode(nodeId);
  }, []);

  // graph 变化回调
  const handleGraphChange = useCallback((nodes: Node<EditorNodeData>[], edges: Edge<EditorEdgeData>[]) => {
    setEditNodes(nodes);
    setEditEdges(edges);
  }, []);

  // v2 (2026-07): 文件模式下，数据加载后自动填充编辑器
  useEffect(() => {
    if (isFileMode && fileData && !yamlText) {
      setYamlText(fileData.raw_content);
      // 对原始 YAML 做一次解析，生成 yamlError（但不阻止编辑器显示）
      const result = parseYamlToPipeline(fileData.raw_content);
      if (!result.success) {
        setYamlError(result.error!);
      }
    }
  }, [isFileMode, fileData, yamlText]);

  // 打开 YAML 编辑器时，用当前 pipeline 生成 YAML
  const handleToggleEditor = useCallback(() => {
    if (!yamlEditorOpen && pipeline) {
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
      // 保留上一次有效的 pipeline，不更新
    }
  }, []);

  // 点击 DAG 节点 → YAML 编辑器滚动到对应行 + 高亮节点
  const handleNodeClick = useCallback((taskId: string) => {
    setSelectedTaskId(taskId || null);
    if (!yamlEditorOpen || !taskId) return;
    // 节点 ID 格式: "subpipeline.taskname"，YAML 中只有 "taskname"
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

  // 显示的 pipeline：编辑器打开时用编辑后的版本，否则用 API 版本
  const displayPipeline: PipelineDetail | undefined = useMemo(() => {
    if (yamlEditorOpen && editedPipeline) return editedPipeline;
    return pipeline;
  }, [yamlEditorOpen, editedPipeline, pipeline]);

  // YAML 光标所在行 → DAG 节点高亮（taskName → node ID 映射）
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

  // 加载状态
  const isLoading = isFileMode ? fileLoading : pipelineLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" />
      </div>
    );
  }

  // 正常模式：pipeline 未找到
  if (!isFileMode && !pipeline) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        流水线未找到
      </div>
    );
  }

  // 文件模式：文件未找到
  if (isFileMode && !fileData) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        文件未找到: {actualFilePath}
      </div>
    );
  }

  const pageTitle = isFileMode ? (fileData?.name || actualFilePath) : pipeline!.name;

  /** 导出 PNG */
  const handleExportPng = async () => {
    const el = graphWrapperRef.current?.querySelector('.react-flow') as HTMLElement | null;
    if (!el) return;
    try {
      await exportAsPng(el, `${pageTitle}.png`);
      message.success('PNG 已导出');
    } catch {
      message.error('导出失败');
    }
  };

  /** 导出 SVG */
  const handleExportSvg = async () => {
    const el = graphWrapperRef.current?.querySelector('.react-flow') as HTMLElement | null;
    if (!el) return;
    try {
      await exportAsSvg(el, `${pageTitle}.svg`);
      message.success('SVG 已导出');
    } catch {
      message.error('导出失败');
    }
  };

  /** 复制到剪贴板 */
  const handleCopy = async () => {
    const el = graphWrapperRef.current?.querySelector('.react-flow') as HTMLElement | null;
    if (!el) return;
    try {
      await copyToClipboard(el);
      message.success('已复制到剪贴板');
    } catch {
      message.error('复制失败，请尝试导出下载');
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* 面包屑 — 显示项目名/流水线名 + 悬浮切换 */}
      <div className="px-4 py-2 border-b border-gray-200 bg-white shrink-0">
        <PipelineBreadcrumb
          projectId={projectId!}
          definitionId={definitionId}
          pipelineName={pipeline?.name}
          isFileMode={isFileMode}
          filePath={actualFilePath}
        />
      </div>

      {/* 工具栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 bg-gray-50 shrink-0">
        <Space>
          {/* v1 (2026-07): issue #206 — 编辑/查看模式切换 */}
          {!isFileMode && (
            <Tooltip title={editMode ? '退出编辑模式' : '进入编辑模式'}>
              <Button
                icon={editMode ? <EyeOutlined /> : <EditOutlined />}
                onClick={() => setEditMode((prev) => !prev)}
                type={editMode ? 'primary' : 'default'}
              >
                {editMode ? '查看模式' : '编辑模式'}
              </Button>
            </Tooltip>
          )}
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
            <>
              <Tooltip title={yamlEditorOpen ? '关闭 YAML 编辑器' : '打开 YAML 编辑器'}>
                <Button
                  icon={yamlEditorOpen ? <CloseOutlined /> : <CodeOutlined />}
                  onClick={handleToggleEditor}
                  type={yamlEditorOpen ? 'primary' : 'default'}
                >
                  {yamlEditorOpen ? '关闭编辑器' : 'YAML 编辑器'}
                </Button>
              </Tooltip>
              {!isFileMode && (
                <>
                  <Tooltip title="导出 PNG">
                    <Button icon={<FileImageOutlined />} onClick={handleExportPng}>
                      导出 PNG
                    </Button>
                  </Tooltip>
                  <Tooltip title="导出 SVG">
                    <Button icon={<ExportOutlined />} onClick={handleExportSvg}>
                      导出 SVG
                    </Button>
                  </Tooltip>
                  <Tooltip title="复制到剪贴板">
                    <Button icon={<CopyOutlined />} onClick={handleCopy}>
                      复制图片
                    </Button>
                  </Tooltip>
                </>
              )}
            </>
          )}
        </Space>
        <Space>
          {isFileMode && (
            <Alert
              type="warning"
              showIcon
              message="YAML 校验失败 — 画布无法渲染，请直接在编辑器中修改"
              style={{ padding: '4px 12px', fontSize: 13 }}
            />
          )}
          {!isFileMode && (
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => setTriggerOpen(true)}
            >
              触发运行
            </Button>
          )}
        </Space>
      </div>

      {/* 主内容区：YAML 编辑器（可选） + DAG 画布/编辑器 + NodePalette */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* YAML 编辑器面板 — 仅查看模式 */}
        {!editMode && yamlEditorOpen && (
          <div className="flex-shrink-0 border-r border-gray-200 bg-[#1e1e1e]" style={{ width: isFileMode ? '100%' : '40%', minWidth: 300 }}>
            <YamlEditor
              ref={yamlEditorRef}
              value={yamlText}
              onChange={handleYamlChange}
              error={yamlError}
              onCursorTaskChange={handleCursorTaskChange}
              onSave={handleSave}
              saving={saving}
            />
          </div>
        )}

        {/* DAG 画布 — 文件模式下隐藏，仅查看模式 */}
        {!isFileMode && !editMode && (
          <div ref={graphWrapperRef} className="flex-1 min-w-0 overflow-hidden flex flex-col">
            {/* v1 (2026-07): issue #195 — 画布错误态横幅 */}
            {yamlEditorOpen && yamlError && (
              <Alert
                type="error"
                showIcon
                banner
                message="当前 YAML 非法，画布展示的是上一次有效版本"
                description={
                  <span className="text-xs">
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
            <div className="flex-1 min-h-0">
              <PipelineGraph pipeline={displayPipeline} onNodeClick={handleNodeClick} selectedTaskId={selectedTaskId} />
            </div>
          </div>
        )}

        {/* 编辑模式 — 可编辑画布 + 右侧节点面板 */}
        {!isFileMode && editMode && (
          <>
            <div className="flex-1 min-w-0 overflow-hidden">
              <WorkflowEditor
                ref={workflowEditorRef}
                pipeline={pipeline!}
                selectedNodeId={selectedTaskId}
                onNodeSelect={handleEditorNodeSelect}
                onGraphChange={handleGraphChange}
                readOnly={!editMode}
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

        {/* 帮助面板 */}
        <HelpPanel
          minimized={helpPanelMinimized}
          onToggleMinimized={toggleHelpPanel}
        />
      </div>

      {/* 触发运行弹窗 — 仅正常模式 */}
      {!isFileMode && (
        <TriggerRunModal
          open={triggerOpen}
          onClose={() => setTriggerOpen(false)}
          defaultDefinitionId={definitionId}
          pipelineData={pipeline!}
        />
      )}
    </div>
  );
}
