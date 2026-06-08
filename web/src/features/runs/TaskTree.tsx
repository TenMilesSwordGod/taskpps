import { useMemo } from 'react';
import { Tree, Tag } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { PartitionOutlined, AppstoreOutlined } from '@ant-design/icons';
import StatusTag from '@/components/StatusTag';
import type { PipelineDetail, TaskStatus, SubPipeline, TaskYAML } from '@/types';

interface TaskTreeProps {
  pipeline: PipelineDetail;
  taskStatuses?: Record<string, TaskStatus>;
  selectedTaskId?: string;
  onSelect: (taskId: string | null) => void;
}

/** 推断任务类型（同 TaskNode） */
function inferTaskType(task: TaskYAML): 'command' | 'invoke' | 'steps' | 'git' | 'nexus' {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

const TYPE_LABEL: Record<string, string> = {
  command: '命令',
  invoke: '调用',
  steps: '步骤',
  git: 'Git',
  nexus: 'Nexus',
};

const TYPE_COLOR: Record<string, string> = {
  command: '#8c8c8c',
  invoke: '#1677ff',
  steps: '#722ed1',
  git: '#fa8c16',
  nexus: '#13c2c2',
};

/** 流水线/任务树形结构切换器 */
export default function TaskTree({ pipeline, taskStatuses, selectedTaskId, onSelect }: TaskTreeProps) {
  const treeData = useMemo<DataNode[]>(() => {
    const subpipelines: SubPipeline[] = pipeline.pipelines || [];
    return subpipelines.map((sub) => {
      const children: DataNode[] = sub.tasks.map((task) => {
        const taskId = `${sub.name}.${task.name}`;
        const status = taskStatuses?.[taskId];
        const type = inferTaskType(task);
        return {
          key: taskId,
          title: (
            <div className="flex items-center gap-2 py-0.5">
              <span style={{ color: TYPE_COLOR[type], fontSize: 12 }}>{TYPE_LABEL[type]}</span>
              <span className="text-sm">{task.name}</span>
              {status && <StatusTag status={status} />}
            </div>
          ),
        };
      });
      return {
        key: `sub-${sub.name}`,
        title: (
          <div className="flex items-center gap-2 py-0.5">
            <PartitionOutlined style={{ color: '#722ed1' }} />
            <span className="text-sm font-medium">{sub.name}</span>
            <Tag>{sub.tasks.length} 个任务</Tag>
          </div>
        ),
        children,
      };
    });
  }, [pipeline, taskStatuses]);

  const selectedKeys = selectedTaskId ? [selectedTaskId] : [];

  return (
    <div style={{ height: '100%', overflow: 'auto', background: '#fafafa', borderRight: '1px solid #e5e7eb' }}>
      <div className="px-3 py-2 border-b border-gray-200 bg-white sticky top-0 z-10">
        <div className="flex items-center gap-1.5">
          <AppstoreOutlined style={{ color: '#1677ff' }} />
          <span className="text-sm font-medium">{pipeline.name}</span>
        </div>
      </div>
      <Tree
        treeData={treeData}
        defaultExpandAll
        selectedKeys={selectedKeys}
        onSelect={(keys) => {
          const key = keys[0] as string | undefined;
          if (key && key.startsWith('sub-')) return; // 子流水线组不切换日志
          onSelect(key ?? null);
        }}
        blockNode
        style={{ padding: '8px 0' }}
      />
    </div>
  );
}
