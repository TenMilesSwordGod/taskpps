import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Breadcrumb, Button, Space, Tooltip, message, Spin } from 'antd';
import {
  ExportOutlined,
  FileImageOutlined,
  CopyOutlined,
  PlayCircleOutlined,
  CodeOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { usePipeline } from '@/api/pipelines';
import PipelineGraph from './PipelineGraph';
import PropertiesPanel from './PropertiesPanel';
import YamlEditor from './YamlEditor';
import type { YamlEditorRef } from './YamlEditor';
import { HelpPanel } from './HelpPanel';
import TriggerRunModal from '@/components/TriggerRunModal';
import { exportAsPng, exportAsSvg, copyToClipboard } from '@/utils/exportImage';
import { useAppStore } from '@/stores/appStore';
import { parseYamlToPipeline, pipelineToYaml } from '@/utils/yamlParser';
import type { PipelineDetail } from '@/types';

/** 流水线详情页 */
export default function PipelineDetailPage() {
  const { file } = useParams<{ file: string }>();
  const navigate = useNavigate();
  const { data: pipeline, isLoading } = usePipeline(file);
  const graphWrapperRef = useRef<HTMLDivElement>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const helpPanelMinimized = useAppStore((s) => s.helpPanelMinimized);
  const toggleHelpPanel = useAppStore((s) => s.toggleHelpPanel);

  // YAML 编辑器状态
  const [yamlEditorOpen, setYamlEditorOpen] = useState(false);
  const [yamlText, setYamlText] = useState('');
  const [yamlError, setYamlError] = useState<{ message: string; line: number; column: number } | null>(null);
  const [editedPipeline, setEditedPipeline] = useState<PipelineDetail | null>(null);
  const yamlEditorRef = useRef<YamlEditorRef>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);

  // 当 API 数据加载后，初始化 YAML 编辑器内容
  useEffect(() => {
    if (pipeline && !yamlEditorOpen) {
      // 首次加载时不需要设置 yamlText，等用户打开编辑器时再生成
    }
  }, [pipeline, yamlEditorOpen]);

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
    const lines = yamlText.split('\n');
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].match(new RegExp(`-\\s+name:\\s+${taskName}\\b`))) {
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spin size="large" />
      </div>
    );
  }

  if (!pipeline) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        流水线未找到
      </div>
    );
  }

  /** 导出 PNG */
  const handleExportPng = async () => {
    const el = graphWrapperRef.current?.querySelector('.react-flow') as HTMLElement | null;
    if (!el) return;
    try {
      await exportAsPng(el, `${pipeline.name}.png`);
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
      await exportAsSvg(el, `${pipeline.name}.svg`);
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
      {/* 面包屑 */}
      <div className="px-4 py-2 border-b border-gray-200 bg-white shrink-0">
        <Breadcrumb
          items={[
            { title: <a onClick={() => navigate('/pipelines')}>流水线</a> },
            { title: file },
          ]}
        />
      </div>

      {/* 工具栏 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100 bg-gray-50 shrink-0">
        <Space>
          <Tooltip title={yamlEditorOpen ? '关闭 YAML 编辑器' : '打开 YAML 编辑器'}>
            <Button
              icon={yamlEditorOpen ? <CloseOutlined /> : <CodeOutlined />}
              onClick={handleToggleEditor}
              type={yamlEditorOpen ? 'primary' : 'default'}
            >
              {yamlEditorOpen ? '关闭编辑器' : 'YAML 编辑器'}
            </Button>
          </Tooltip>
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
        </Space>
        <Space>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={() => setTriggerOpen(true)}
          >
            触发运行
          </Button>
        </Space>
      </div>

      {/* 主内容区：YAML 编辑器（可选） + DAG 画布 + 属性面板 */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* YAML 编辑器面板 */}
        {yamlEditorOpen && (
          <div className="flex-shrink-0 border-r border-gray-200 bg-[#1e1e1e]" style={{ width: '40%', minWidth: 300 }}>
            <YamlEditor
              ref={yamlEditorRef}
              value={yamlText}
              onChange={handleYamlChange}
              error={yamlError}
              onCursorTaskChange={handleCursorTaskChange}
            />
          </div>
        )}

        {/* DAG 画布 */}
        <div ref={graphWrapperRef} className="flex-1 min-w-0 overflow-hidden">
          <PipelineGraph pipeline={displayPipeline} onNodeClick={handleNodeClick} selectedTaskId={selectedTaskId} />
        </div>

        {/* 帮助面板 + 属性面板 */}
        <HelpPanel
          minimized={helpPanelMinimized}
          onToggleMinimized={toggleHelpPanel}
        />
        <PropertiesPanel pipeline={displayPipeline} />
      </div>

      {/* 触发运行弹窗 */}
      <TriggerRunModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        defaultPipeline={file}
        pipelineData={pipeline}
      />
    </div>
  );
}
