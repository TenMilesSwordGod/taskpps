import { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Breadcrumb, Button, Space, Tooltip, message, Spin } from 'antd';
import {
  ExportOutlined,
  FileImageOutlined,
  CopyOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { usePipeline } from '@/api/pipelines';
import PipelineGraph from './PipelineGraph';
import PropertiesPanel from './PropertiesPanel';
import { HelpPanel } from './HelpPanel';
import TriggerRunModal from '@/components/TriggerRunModal';
import { exportAsPng, exportAsSvg, copyToClipboard } from '@/utils/exportImage';
import { useAppStore } from '@/stores/appStore';

/** 流水线详情页 */
export default function PipelineDetailPage() {
  const { file } = useParams<{ file: string }>();
  const navigate = useNavigate();
  const { data: pipeline, isLoading } = usePipeline(file);
  const graphWrapperRef = useRef<HTMLDivElement>(null);
  const [triggerOpen, setTriggerOpen] = useState(false);
  const helpPanelMinimized = useAppStore((s) => s.helpPanelMinimized);
  const toggleHelpPanel = useAppStore((s) => s.toggleHelpPanel);

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

      {/* 主内容区：DAG 画布 + 属性面板 */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div ref={graphWrapperRef} className="flex-1 min-w-0 overflow-hidden">
          <PipelineGraph pipeline={pipeline} />
        </div>
        <HelpPanel
          minimized={helpPanelMinimized}
          onToggleMinimized={toggleHelpPanel}
        />
        <PropertiesPanel pipeline={pipeline} />
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
