import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Space, Tooltip, message, Spin, Alert, Modal, Dropdown, Tag } from 'antd';
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
  DownOutlined,
} from '@ant-design/icons';
import { usePipelineById, usePipelineByFile, useSavePipelineById, useSavePipelineByFile } from '@/api/pipelines';
import YamlEditor from './YamlEditor';
import type { YamlEditorRef, VariableHoverData } from './YamlEditor';
import { HelpPanel } from './HelpPanel';
import TriggerRunModal from '@/components/TriggerRunModal';
import PipelineBreadcrumb from '@/components/PipelineBreadcrumb';
import { exportAsPng, exportAsSvg, copyToClipboard } from '@/utils/exportImage';
import { useAppStore } from '@/stores/appStore';
import { parseYamlToPipeline, pipelineToYaml } from '@/utils/yamlParser';
import type { PipelineDetail, ValidationError } from '@/types';
import { buildVariableIndex, type AgentVariableSource, type CredentialVariableSource } from '@/utils/yamlVariables';
import { useIsAdmin } from '@/hooks/useIsAdmin';
import { useAgentsWithConfig } from '@/api/agents';
import { useCredentials } from '@/api/credentials';
import WorkflowEditor, { type WorkflowEditorRef } from './workflow/WorkflowEditor';
import NodePalette from './workflow/NodePalette';
import PropertyPanel from './workflow/PropertyPanel';
import { nodesToYaml } from './workflow/nodesToYaml';
import { yamlToNodes } from './workflow/yamlToNodes';
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
  // v6 (2026-08): critique P1 — YAML 草稿保护。
  // 此前每次打开编辑器都 pipelineToYaml() 覆盖 yamlText，「打字→没保存→关闭→重开」
  // 草稿静默蒸发，且与编辑模式（有确认+beforeunload）双标。现在跟踪 dirty：
  // 有未保存修改时关闭需确认、重开恢复草稿、保存成功后自动清零。
  const [yamlDirty, setYamlDirty] = useState(false);
  // v6 (2026-08): 记录当前 yamlText 基于哪个数据源生成 ——
  // 仅当「非 dirty 且数据源已变化」才允许重新生成，否则保留编辑器现有文本。
  // v7 (2026-08): 从 pipeline 对象引用改为「数据源 key」（definitionId / 文件路径）。
  //   保存后 invalidate → refetch 在结构变化时会换对象引用，旧逻辑误判为换流水线
  //   并重新序列化，把用户注释/格式吞掉；key 只随路由参数变化。
  const yamlSourceKey = isFileMode ? `file:${actualFilePath ?? ''}` : `id:${definitionId ?? ''}`;
  const yamlSourceRef = useRef<string | null>(null);

  // v7 (2026-08): 编辑器初始文本优先用磁盘原文（保留注释/空行/字段顺序），
  // 仅当后端未返回 raw_content（旧数据/空串）时回退到结构化序列化
  const pipelineEditorText = useCallback(
    (p: PipelineDetail) =>
      p.raw_content && p.raw_content.trim() ? p.raw_content : pipelineToYaml(p),
    [],
  );

  // v7 (2026-08): P1 跨流水线串稿修复 —— 切换流水线/文件时组件不会重新挂载，
  // 必须清掉上一份 YAML 草稿，否则保存会把 A 的内容写入 B。
  // 用 ref 记录上一个 key，避免首次挂载/普通 re-render 触发清空。
  const prevYamlSourceKeyRef = useRef(yamlSourceKey);
  useEffect(() => {
    if (prevYamlSourceKeyRef.current === yamlSourceKey) return;
    prevYamlSourceKeyRef.current = yamlSourceKey;
    setYamlText('');
    setYamlError(null);
    setEditedPipeline(null);
    setYamlDirty(false);
    yamlSourceRef.current = null;
  }, [yamlSourceKey]);

  // v7 (2026-08): 换源后编辑器仍开着时，等新 pipeline 到达自动填充
  //（文件模式由下方 fileData 的 effect 负责）
  useEffect(() => {
    if (!isFileMode && yamlEditorOpen && pipeline && yamlSourceRef.current === null) {
      const yaml = pipelineEditorText(pipeline);
      setYamlText(yaml);
      yamlSourceRef.current = yamlSourceKey;
      setEditedPipeline(null);
      setYamlError(null);
    }
  }, [isFileMode, yamlEditorOpen, pipeline, yamlSourceKey, pipelineEditorText]);

  // v1 (2026-07): issue #206 — 可视化编辑器模式
  const [editMode, setEditMode] = useState(false);
  // v4 (2026-07): dirty 状态驱动"保存"按钮 disabled；保存成功后清除
  const [editorDirty, setEditorDirty] = useState(false);
  const [editNodes, setEditNodes] = useState<Node<EditorNodeData>[]>([]);
  const [editEdges, setEditEdges] = useState<Edge<EditorEdgeData>[]>([]);
  const [propertyPanelVisible, setPropertyPanelVisible] = useState(false);
  const [editingNode, setEditingNode] = useState<Node<EditorNodeData> | null>(null);
  const workflowEditorRef = useRef<WorkflowEditorRef>(null);
  // 进入编辑模式时是否已用 yamlToNodes(pipeline) 初始化过 editNodes/editEdges。
  // 用 ref 防重入：避免后续 render 因 pipeline 引用变化而覆盖用户在画布上的编辑结果。
  const editInitializedRef = useRef(false);

  // 保存：正常模式用 by-id，文件模式用 by-file
  const saveByIdMutation = useSavePipelineById(!isFileMode ? definitionId : undefined);
  const saveByFileMutation = useSavePipelineByFile(isFileMode ? projectId : undefined);

  const saving = isFileMode ? saveByFileMutation.isPending : saveByIdMutation.isPending;

  const handleSave = useCallback((contentOverride?: string) => {
    // v7 (2026-08): 优先使用编辑器冲刷出的最新内容，避免 debounce 窗口内保存丢输入
    const content = contentOverride ?? yamlText;
    if (!content.trim()) {
      // 旧实现直接 return，点击保存毫无反馈；空内容无法构成流水线，明确报错
      message.error('YAML 内容为空，无法保存');
      return;
    }
    // v7 (2026-08): 请求进行中忽略重复触发（Ctrl+S 不受按钮 loading 限制）
    if (saving) return;
    // v5 (2026-09, issue #216): 保存成功后清除未保存标记
    const onSuccess = () => {
      message.success('已保存');
      setYamlDirty(false);
    };
    if (isFileMode && actualFilePath) {
      saveByFileMutation.mutate({ file: actualFilePath, content }, {
        onSuccess,
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    } else if (definitionId) {
      saveByIdMutation.mutate(content, {
        onSuccess,
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    }
  }, [yamlText, saving, isFileMode, actualFilePath, definitionId, saveByFileMutation, saveByIdMutation]);

  // v1 (2026-07): issue #206 — 编辑器中保存：nodes/edges → YAML → 写回
  const handleSaveFromEditor = useCallback(() => {
    // v7 (2026-08): 与 YAML 保存一致，请求进行中忽略重复触发
    if (saving) return;
    const { pipeline: editedPipeline, errors } = nodesToYaml(editNodes, editEdges);
    if (!editedPipeline) {
      message.error(`保存失败: ${errors.join(', ')}`);
      return;
    }
    const yaml = pipelineToYaml(editedPipeline);
    const onSuccess = () => {
      message.success('已保存');
      // v4 (2026-07): 保存成功后清除 dirty（保存按钮回到 disabled，离开守卫同步重置）
      workflowEditorRef.current?.markClean();
      setEditorDirty(false);
    };
    if (isFileMode && actualFilePath) {
      saveByFileMutation.mutate({ file: actualFilePath, content: yaml }, {
        onSuccess,
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    } else if (definitionId) {
      saveByIdMutation.mutate(yaml, {
        onSuccess,
        onError: (err: Error) => message.error(`保存失败: ${err.message}`),
      });
    }
  }, [editNodes, editEdges, saving, isFileMode, actualFilePath, definitionId, saveByFileMutation, saveByIdMutation]);

  // v2 (2026-07): 未保存修改的离开守卫
  // v5 (2026-09, issue #216): 守卫范围从「仅编辑模式」扩展到「编辑模式或查看模式 YAML 编辑器」；
  // 查看模式没有 workflowEditorRef，用 yamlDirtyRef 读取最新值（避免闭包过期）。
  const yamlDirtyRef = useRef(false);
  useEffect(() => {
    yamlDirtyRef.current = yamlDirty;
  }, [yamlDirty]);

  useEffect(() => {
    if (!editMode && !yamlEditorOpen) return;
    const handler = (e: BeforeUnloadEvent) => {
      if (workflowEditorRef.current?.isDirty || yamlDirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [editMode, yamlEditorOpen]);

  // v5 (2026-09, issue #216): 补齐「保存 (Ctrl+S)」提示承诺的快捷键（旧实现仅画布支持 Delete/Backspace）
  useEffect(() => {
    if (!editMode) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        handleSaveFromEditor();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [editMode, handleSaveFromEditor]);

  // v4 (2026-07): 退出编辑模式时清除 dirty 指示，避免残留到下次进入
  useEffect(() => {
    if (!editMode) setEditorDirty(false);
  }, [editMode]);

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
  // v4 (2026-07): 同步画布内部状态，否则属性面板改名后画布节点文字不变
  const handlePropertySave = useCallback((updatedNode: Node<EditorNodeData>) => {
    workflowEditorRef.current?.updateNode(updatedNode);
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

  // v2 (2026-07): issue #206 / bug #39 — 进入编辑模式时必须用 yamlToNodes(pipeline)
  // 初始化 editNodes/editEdges。否则 WorkflowEditor 仅在保存/连线时触发 onGraphChange，
  // 初始不回调，导致 editNodes 长期为空；保存时 nodesToYaml([],[]) 找不到 __pipeline__
  // 节点而得到 name='unnamed'、pipelines=[]。这里与 WorkflowEditor 内部节点 ID 对齐，
  // 保证保存序列化能还原真实流水线名与 SubPipeline/Task 结构。
  // 退出编辑模式时重置标记，使再次进入能重新从最新 pipeline 初始化。
  // v3 (2026-07): 数据源改为 displayPipeline —— 查看模式 YAML 编辑器里的未保存修改
  // 必须带入编辑模式，否则切换时画布回退到 API 旧数据（e2e 压力测试暴露的不一致）。
  useEffect(() => {
    if (editMode && !isFileMode && pipeline) {
      if (!editInitializedRef.current) {
        const source = yamlEditorOpen && editedPipeline ? editedPipeline : pipeline;
        const g = yamlToNodes(source);
        setEditNodes(g.nodes);
        setEditEdges(g.edges);
        editInitializedRef.current = true;
      }
    } else {
      editInitializedRef.current = false;
    }
  }, [editMode, pipeline, editedPipeline, yamlEditorOpen, isFileMode]);

  // v2 (2026-07): 文件模式下，数据加载后自动填充编辑器
  useEffect(() => {
    if (isFileMode && fileData && !yamlText) {
      setYamlText(fileData.raw_content);
      yamlSourceRef.current = yamlSourceKey;
      // 对原始 YAML 做一次解析，生成 yamlError（但不阻止编辑器显示）
      const result = parseYamlToPipeline(fileData.raw_content);
      if (!result.success) {
        setYamlError(result.error!);
      }
    }
  }, [isFileMode, fileData, yamlText, yamlSourceKey]);

  // v7 (2026-08): YAML 草稿的 beforeunload 守卫（与编辑模式对齐）。
  // 旧实现只在 editMode 注册，view 模式下有未保存 YAML 时刷新/关标签页静默丢稿。
  useEffect(() => {
    if (!yamlEditorOpen || !yamlDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [yamlEditorOpen, yamlDirty]);

  // 打开/关闭 YAML 编辑器
  // v6 (2026-08): critique P1 — 草稿保护重写切换逻辑：
  //   打开时：有未保存草稿则恢复草稿（不重新生成），仅无文本或已同步时才从 pipeline 生成；
  //   关闭时：dirty 需确认丢弃，防止「打字→没保存→关闭→重开」静默丢稿。
  const handleToggleEditor = useCallback(() => {
    if (yamlEditorOpen) {
      if (yamlDirty) {
        Modal.confirm({
          title: '放弃未保存的 YAML 修改？',
          content: '关闭编辑器将丢失未保存的内容。',
          okText: '放弃并关闭',
          okButtonProps: { danger: true },
          cancelText: '继续编辑',
          onOk: () => {
            // v6 (2026-08): e2e 实测发现仅关面板不清草稿，「放弃」名不副实。
            // 放弃 = 回到最后一次已保存状态：重新生成 YAML、清除草稿标记
            if (pipeline) {
              const yaml = pipelineEditorText(pipeline);
              setYamlText(yaml);
              yamlSourceRef.current = yamlSourceKey;
              setEditedPipeline(null);
              setYamlError(null);
            } else if (isFileMode && fileData) {
              // v7 (2026-08): 文件模式 pipeline 为 undefined，旧实现跳过还原，
              // 「放弃并关闭」后草稿仍残留；这里显式回到磁盘原文
              setYamlText(fileData.raw_content);
              const result = parseYamlToPipeline(fileData.raw_content);
              setYamlError(result.success ? null : result.error!);
              setEditedPipeline(null);
              yamlSourceRef.current = yamlSourceKey;
            }
            setYamlDirty(false);
            setYamlEditorOpen(false);
          },
        });
        return;
      }
      setYamlEditorOpen(false);
      return;
    }
    // 打开：草稿优先 —— 仅在「无任何文本」或「非 dirty 且数据源已变化」时重新生成；
    // 其余情况保留编辑器现有文本（用户草稿 / 已保存的用户格式）。
    // v3 (2026-09, issue #216): pipelineEditorText 优先返回后端 raw_content（磁盘原文），
    // 避免已解析模型丢失 schema 未声明字段；旧数据为空时回退 pipelineToYaml。
    if (pipeline && (!yamlText || (!yamlDirty && yamlSourceRef.current !== yamlSourceKey))) {
      const yaml = pipelineEditorText(pipeline);
      setYamlText(yaml);
      yamlSourceRef.current = yamlSourceKey;
      setEditedPipeline(null);
      setYamlError(null);
      setYamlDirty(false);
    }
    setYamlEditorOpen(true);
  }, [yamlEditorOpen, pipeline, yamlDirty, yamlText, yamlSourceKey, isFileMode, fileData, pipelineEditorText]);

  // YAML 内容变化时解析并更新流程图
  const handleYamlChange = useCallback((text: string) => {
    setYamlText(text);
    // v6 (2026-08): 用户输入即产生未保存草稿
    // v5 (2026-09, issue #216): 任何编辑都标记未保存，供工具栏与 beforeunload 使用
    setYamlDirty(true);
    const result = parseYamlToPipeline(text);
    if (result.success) {
      setEditedPipeline(result.pipeline!);
      setYamlError(null);
    } else {
      setYamlError(result.error!);
      // 保留上一次有效的 pipeline，不更新
    }
  }, []);

  // 查看模式点击画布节点 → 选中 + YAML 编辑器滚动到对应行
  // v3 (2026-07): 统一为 WorkflowEditor 后节点 ID 为 __task__<sub>.<task> 格式
  const handleViewNodeSelect = useCallback((nodeId: string | null) => {
    setSelectedTaskId(nodeId);
    if (!nodeId || !yamlEditorOpen) return;
    const taskName = nodeId.startsWith('__task__')
      ? nodeId.slice('__task__'.length).split('.').pop()!
      : nodeId;
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

  // YAML 光标所在行 → 画布节点高亮（taskName → 编辑器节点 ID 映射）
  // v3 (2026-07): 查看模式统一为 WorkflowEditor 后节点 ID 使用 __task__<sub>.<task>，
  // 不再使用旧只读图的 <sub>.<task>；顶层 tasks 编辑器不支持（与编辑模式一致）。
  const taskNameToNodeId = useMemo(() => {
    const map = new Map<string, string>();
    const p = displayPipeline;
    if (!p) return map;
    p.pipelines?.forEach((sub) => {
      sub.tasks?.forEach((t) => {
        map.set(t.name, `__task__${sub.name}.${t.name}`);
      });
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

  // v3 (2026-09): YAML 编辑器 ${...} 悬浮解析数据。
  // 仅在文本确实含对应引用时才拉项目配置，避免无变量流水线也发请求；
  // agent 快照关掉 5s 轮询（悬浮只需要静态配置），凭据接口仅管理员可用，
  // 非管理员展示"需管理员权限"而不是误报"未找到"。
  const isAdmin = useIsAdmin();
  const hasAgentRef = yamlText.includes('${agent:');
  const hasCredentialRef = yamlText.includes('${credential:');
  const { data: agentsWithConfig } = useAgentsWithConfig(hasAgentRef, { refetchInterval: false });
  const { data: credentials } = useCredentials(projectId, hasCredentialRef && isAdmin);

  const variableHover = useMemo<VariableHoverData | undefined>(() => {
    if (!yamlText) return undefined;
    const agentMap = new Map<string, AgentVariableSource>();
    for (const agent of agentsWithConfig ?? []) {
      agentMap.set(agent.agent_id, agent);
      if (agent.name) agentMap.set(agent.name, agent);
    }
    const credentialMap = new Map<string, CredentialVariableSource>();
    for (const credential of credentials ?? []) {
      credentialMap.set(credential.id, credential);
      credentialMap.set(credential.name, credential);
    }
    return {
      index: buildVariableIndex(yamlText),
      agents: agentMap,
      credentials: credentialMap,
      credentialsUnavailable: hasCredentialRef && !isAdmin,
    };
  }, [yamlText, agentsWithConfig, credentials, hasCredentialRef, isAdmin]);

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
      {/* v11 (2026-08): 单行顶栏 —— 面包屑居左、操作居右。
          旧版面包屑+工具栏两行通栏占 ~90px 且五个等权重按钮成"按钮汤"；
          合并后垂直空间还给画布，导出三动作收敛为下拉（n8n 顶栏语汇） */}
      <div
        className="flex items-center justify-between gap-3 px-4 py-2 border-b bg-white shrink-0"
        style={{ borderColor: '#E8EBF0' }}
      >
        <div className="flex items-center min-w-0 overflow-hidden">
          <PipelineBreadcrumb
            projectId={projectId!}
            definitionId={definitionId}
            pipelineName={pipeline?.name}
            isFileMode={isFileMode}
            filePath={actualFilePath}
          />
        </div>

        <Space className="flex items-center">
          {/* v1 (2026-07): issue #206 — 编辑/查看模式切换 */}
          {!isFileMode && (
              <Tooltip title={editMode ? '退出编辑模式' : '进入编辑模式'} placement="bottom">
                <Button
                  icon={editMode ? <EyeOutlined /> : <EditOutlined />}
                  onClick={() => {
                    // v2 (2026-07): 切换到查看模式前检查未保存修改
                    if (editMode && workflowEditorRef.current?.isDirty) {
                      Modal.confirm({
                        title: '未保存的修改',
                        content: '退出编辑模式将丢失所有未保存的修改，确定继续？',
                        okText: '确定退出',
                        cancelText: '继续编辑',
                        okButtonProps: { danger: true },
                        onOk: () => setEditMode(false),
                      });
                    } else {
                      setEditMode((prev) => !prev);
                    }
                  }}
                  type={editMode ? 'primary' : 'default'}
                >
                  {editMode ? '查看模式' : '编辑模式'}
                </Button>
              </Tooltip>
          )}
          {editMode && (
            <Tooltip title="保存 (Ctrl+S)" placement="bottom">
              <Button
                icon={<SaveOutlined />}
                onClick={handleSaveFromEditor}
                loading={saving}
                disabled={!editorDirty}
                type="primary"
              >
                保存
              </Button>
            </Tooltip>
          )}
          {!editMode && (
            <>
              <Tooltip title={yamlEditorOpen ? '关闭 YAML 编辑器' : '打开 YAML 编辑器'} placement="bottom">
                <Button
                  icon={yamlEditorOpen ? <CloseOutlined /> : <CodeOutlined />}
                  onClick={handleToggleEditor}
                  type={yamlEditorOpen ? 'primary' : 'default'}
                >
                  {yamlEditorOpen ? '关闭编辑器' : 'YAML 编辑器'}
                </Button>
                {/* v5 (2026-09, issue #216): 查看模式 YAML 修改后的未保存提示 */}
                {yamlEditorOpen && yamlDirty && <Tag color="warning">未保存</Tag>}
              </Tooltip>
              {!isFileMode && (
                // v11: 导出三动作（PNG/SVG/复制）收敛为下拉 —— 降低顶栏按钮密度，
                // 低频动作不与高频动作（编辑模式/YAML）抢占同等视觉权重
                <Dropdown
                  placement="bottomRight"
                  menu={{
                    items: [
                      { key: 'png', icon: <FileImageOutlined />, label: '导出 PNG', onClick: handleExportPng },
                      { key: 'svg', icon: <ExportOutlined />, label: '导出 SVG', onClick: handleExportSvg },
                      { key: 'copy', icon: <CopyOutlined />, label: '复制图片', onClick: handleCopy },
                    ],
                  }}
                >
                  <Button icon={<ExportOutlined />}>
                    导出 <DownOutlined style={{ fontSize: 10 }} />
                  </Button>
                </Dropdown>
              )}
            </>
          )}
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
              // v6 (2026-08): critique P2 — 高风险时机守卫：编辑模式有未保存修改时，
              // 运行的将是服务器上已保存的旧版本，须让用户显式确认而非静默执行
              onClick={() => {
                if (editMode && workflowEditorRef.current?.isDirty) {
                  Modal.confirm({
                    title: '画布存在未保存的修改',
                    content: '本次运行将使用服务器上最近保存的版本，画布中的修改不会被包含。',
                    okText: '仍要运行',
                    cancelText: '返回保存',
                    onOk: () => setTriggerOpen(true),
                  });
                  return;
                }
                setTriggerOpen(true);
              }}
            >
              触发运行
            </Button>
          )}
        </Space>
      </div>

      {/* 主内容区：YAML 编辑器（可选） + DAG 画布/编辑器 + NodePalette */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* YAML 编辑器面板 — 仅查看模式。v5 (2026-08): 容器从深色 #1e1e1e 改白底，与画布 n8n 浅色风格统一 */}
        {!editMode && yamlEditorOpen && (
          <div className="flex-shrink-0 border-r border-gray-200 bg-white" style={{ width: isFileMode ? '100%' : '40%', minWidth: 300 }}>
            <YamlEditor
              ref={yamlEditorRef}
              value={yamlText}
              onChange={handleYamlChange}
              error={yamlError}
              onCursorTaskChange={handleCursorTaskChange}
              onSave={handleSave}
              saving={saving}
              variableHover={variableHover}
            />
          </div>
        )}

        {/* DAG 画布 — 文件模式下隐藏，仅查看模式
            v3 (2026-07): 查看模式复用 WorkflowEditor（readOnly），与编辑模式同一套
            图模型/布局/节点视觉，删除旧只读 PipelineGraph 双轨渲染。 */}
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
              <WorkflowEditor
                pipeline={displayPipeline}
                selectedNodeId={selectedTaskId}
                onNodeSelect={handleViewNodeSelect}
                readOnly
              />
            </div>
          </div>
        )}

        {/* 编辑模式 — 可编辑画布 + 右侧节点面板 */}
        {!isFileMode && editMode && (
          <>
            <div className="flex-1 min-w-0 overflow-hidden">
              <WorkflowEditor
                ref={workflowEditorRef}
                pipeline={displayPipeline}
                selectedNodeId={selectedTaskId}
                onNodeSelect={handleEditorNodeSelect}
                onGraphChange={handleGraphChange}
                onDirtyChange={setEditorDirty}
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
