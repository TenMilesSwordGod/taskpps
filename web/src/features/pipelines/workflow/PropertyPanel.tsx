import { useMemo, useCallback, useState } from 'react';
import { Drawer, Input, Select, InputNumber, Button, Space, Divider, Typography, Collapse } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import type { Node, Edge } from '@xyflow/react';
import type { TaskYAML, TaskType, PipelineConfig } from '@/types';
import type { EditorNodeData, EditorEdgeData } from './yamlToNodes';
import { FONT_MONO } from '@/features/pipelines/nodes/nodeTokens';

const { TextArea } = Input;
const { Text } = Typography;

/**
 * 属性编辑面板 — 浮动 Drawer
 * 选中节点后在右侧弹出，编辑完关闭
 *
 * 支持节点类型:
 *   - editorTask: 编辑 Task 所有属性
 *   - editorSubPipeline: 编辑 SubPipeline 配置
 *   - editorPostParent: 编辑 Post 父容器
 *   - editorPostChild: 编辑 Post 子容器
 *   - editorStartEnd: 极简编辑
 *   - editorPipeline: 编辑 Pipeline 配置
 */

interface PropertyPanelProps {
  selectedNode: Node<EditorNodeData> | null;
  visible: boolean;
  onClose: () => void;
  onSave: (updatedNode: Node<EditorNodeData>) => void;
  onDelete: (nodeId: string) => void;
}

export default function PropertyPanel({ selectedNode, visible, onClose, onSave, onDelete }: PropertyPanelProps) {
  const [editData, setEditData] = useState<Record<string, unknown>>({});

  // 初始化编辑数据
  useMemo(() => {
    if (selectedNode?.data) {
      const task = selectedNode.data?.task as TaskYAML | undefined;
      setEditData({
        name: task?.name || selectedNode.data?.label || '',
        description: (task as unknown as Record<string, string>)?.description || '',
        command: task?.command || '',
        cwd: task?.cwd || '',
        timeout: task?.timeout || 300,
        retry: task?.retry || 0,
        when: task?.when || '',
        executionStrategy: selectedNode.data?.executionStrategy || 'sequential',
        maxConcurrentTasks: selectedNode.data?.maxConcurrentTasks || 5,
        on_failure: task?.on_failure || 'stop',
      });
    }
  }, [selectedNode?.id]);

  const handleSave = useCallback(() => {
    if (!selectedNode) return;

    const updatedNode = { ...selectedNode };
    const task = updatedNode.data?.task as TaskYAML | undefined;

    if (task) {
      // 更新 task 字段
      updatedNode.data = {
        ...updatedNode.data,
        task: {
          ...task,
          name: (editData.name as string) || task.name,
          command: (editData.command as string) || task.command,
          cwd: (editData.cwd as string) || undefined,
          timeout: (editData.timeout as number) || undefined,
          retry: (editData.retry as number) || 0,
          when: (editData.when as string) || undefined,
          on_failure: (editData.on_failure as string) || undefined,
        },
      };
    }

    // 更新容器类型节点
    if (selectedNode.type === 'editorSubPipeline' || selectedNode.type === 'editorPipeline') {
      updatedNode.data = {
        ...updatedNode.data,
        label: editData.name as string,
        executionStrategy: editData.executionStrategy as string,
        maxConcurrentTasks: editData.maxConcurrentTasks as number,
      };
    }

    onSave(updatedNode);
    onClose();
  }, [selectedNode, editData, onSave, onClose]);

  const handleDelete = useCallback(() => {
    if (selectedNode) {
      onDelete(selectedNode.id);
      onClose();
    }
  }, [selectedNode, onDelete, onClose]);

  if (!selectedNode) return null;

  const nodeType = selectedNode.type;
  const task = selectedNode.data?.task as TaskYAML | undefined;
  const isContainer = nodeType === 'editorSubPipeline' || nodeType === 'editorPipeline';
  const isTask = nodeType === 'editorTask';
  const isPost = nodeType === 'editorPostChild';

  const title = task?.name || selectedNode.data?.label || '节点属性';

  return (
    <Drawer
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CloseOutlined onClick={onClose} style={{ cursor: 'pointer' }} />
          <span style={{ fontFamily: FONT_MONO, fontSize: 14, fontWeight: 600 }}>
            属性编辑 — {title}
          </span>
        </div>
      }
      placement="right"
      open={visible}
      onClose={onClose}
      width={380}
      mask={false}
      styles={{ body: { padding: '16px' } }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* 名称 */}
        <div>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>名称</Text>
          <Input
            size="small"
            value={(editData.name as string) || ''}
            onChange={(e) => setEditData((d) => ({ ...d, name: e.target.value }))}
            style={{ fontFamily: FONT_MONO }}
          />
        </div>

        {/* 描述 */}
        {(isTask || isPost) && (
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>描述</Text>
            <Input
              size="small"
              value={(editData.description as string) || ''}
              onChange={(e) => setEditData((d) => ({ ...d, description: e.target.value }))}
            />
          </div>
        )}

        <Divider style={{ margin: '4px 0' }} />

        {/* 命令 (CMD) */}
        {isTask && (
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>命令</Text>
            <TextArea
              size="small"
              rows={3}
              value={(editData.command as string) || ''}
              onChange={(e) => setEditData((d) => ({ ...d, command: e.target.value }))}
              style={{ fontFamily: FONT_MONO, fontSize: 12 }}
            />
          </div>
        )}

        {/* 工作目录 */}
        {isTask && (
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>工作目录</Text>
            <Input
              size="small"
              value={(editData.cwd as string) || ''}
              onChange={(e) => setEditData((d) => ({ ...d, cwd: e.target.value }))}
              style={{ fontFamily: FONT_MONO }}
              placeholder="/home/user"
            />
          </div>
        )}

        {/* 执行策略 (容器节点) */}
        {isContainer && (
          <>
            <div>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>执行策略</Text>
              <Select
                size="small"
                value={(editData.executionStrategy as string) || 'sequential'}
                onChange={(v) => setEditData((d) => ({ ...d, executionStrategy: v }))}
                style={{ width: '100%' }}
                options={[
                  { value: 'sequential', label: '顺序 (sequential)' },
                  { value: 'parallel', label: '并发 (parallel)' },
                ]}
              />
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>最大并发数</Text>
              <InputNumber
                size="small"
                min={1}
                max={20}
                value={(editData.maxConcurrentTasks as number) || 5}
                onChange={(v) => setEditData((d) => ({ ...d, maxConcurrentTasks: v }))}
                style={{ width: '100%' }}
              />
            </div>
          </>
        )}

        {/* when 条件 */}
        {isTask && (
          <>
            <Divider style={{ margin: '4px 0' }} />
            <div>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>When 条件</Text>
              <Input
                size="small"
                value={(editData.when as string) || ''}
                onChange={(e) => setEditData((d) => ({ ...d, when: e.target.value }))}
                style={{ fontFamily: FONT_MONO }}
                placeholder="\${env.BRANCH} == main"
              />
            </div>
          </>
        )}

        {/* timeout / retry */}
        {isTask && (
          <>
            <Divider style={{ margin: '4px 0' }} />
            <div style={{ display: 'flex', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>超时 (秒)</Text>
                <InputNumber
                  size="small"
                  min={0}
                  value={(editData.timeout as number) || 300}
                  onChange={(v) => setEditData((d) => ({ ...d, timeout: v }))}
                  style={{ width: '100%' }}
                />
              </div>
              <div style={{ flex: 1 }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>重试次数</Text>
                <InputNumber
                  size="small"
                  min={0}
                  max={10}
                  value={(editData.retry as number) || 0}
                  onChange={(v) => setEditData((d) => ({ ...d, retry: v }))}
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          </>
        )}

        {/* on_failure */}
        {isTask && (
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>失败策略</Text>
            <Select
              size="small"
              value={(editData.on_failure as string) || 'stop'}
              onChange={(v) => setEditData((d) => ({ ...d, on_failure: v }))}
              style={{ width: '100%' }}
              options={[
                { value: 'stop', label: '停止 (stop)' },
                { value: 'ignore', label: '忽略 (ignore)' },
                { value: 'retry', label: '重试 (retry)' },
              ]}
            />
          </div>
        )}

        <Divider style={{ margin: '8px 0' }} />

        {/* 操作按钮 */}
        <Space style={{ justifyContent: 'space-between', width: '100%' }}>
          <Button danger size="small" onClick={handleDelete}>
            删除节点
          </Button>
          <Space>
            <Button size="small" onClick={onClose}>取消</Button>
            <Button type="primary" size="small" onClick={handleSave}>确认</Button>
          </Space>
        </Space>
      </div>
    </Drawer>
  );
}
