import { useMemo } from 'react';
import { Modal, Tag, Descriptions } from 'antd';
import { marked } from 'marked';
import type { PluginResponse, PluginType } from '@/types';

const TYPE_LABELS: Record<PluginType, string> = {
  TriggerPlugin: '触发器',
  NotifierPlugin: '通知器',
  ExecutorPlugin: '执行器',
};

interface PluginDetailModalProps {
  plugin: PluginResponse | null;
  onClose: () => void;
}

export default function PluginDetailModal({ plugin, onClose }: PluginDetailModalProps) {
  const renderedHelp = useMemo(() => {
    if (!plugin?.help_msg) return '';
    return marked.parse(plugin.help_msg) as string;
  }, [plugin?.help_msg]);

  if (!plugin) return null;

  return (
    <Modal
      title={plugin.name}
      open={!!plugin}
      onCancel={onClose}
      footer={null}
      width={640}
      destroyOnClose
    >
      <Descriptions column={2} bordered size="small" className="mb-4">
        <Descriptions.Item label="类型">
          <Tag color="blue">{TYPE_LABELS[plugin.type as PluginType] ?? plugin.type}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="版本">
          <Tag>{plugin.version}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="启用">
          <Tag color={plugin.enabled ? 'success' : 'default'}>
            {plugin.enabled ? '已启用' : '已关闭'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="运行状态">
          {plugin.status ? (
            <Tag color={
              plugin.status === 'loaded' ? 'success' :
              plugin.status === 'crashed' ? 'error' :
              plugin.status === 'db_only' ? 'warning' : 'default'
            }>{plugin.status}</Tag>
          ) : (
            <Tag>unknown</Tag>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {new Date(plugin.created_at).toLocaleString()}
        </Descriptions.Item>
      </Descriptions>

      <div className="border border-gray-200 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3">帮助信息</h4>
        {renderedHelp ? (
          <div
            className="prose prose-sm max-w-none text-gray-600 text-xs leading-relaxed"
            dangerouslySetInnerHTML={{ __html: renderedHelp }}
          />
        ) : (
          <div className="text-gray-400 text-xs">(无帮助信息)</div>
        )}
      </div>
    </Modal>
  );
}
