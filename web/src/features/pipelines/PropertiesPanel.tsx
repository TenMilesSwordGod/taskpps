import { useMemo } from 'react';
import {
  Tabs,
  Input,
  Tag,
  Descriptions,
  Button,
  Tooltip,
} from 'antd';
import {
  MinusOutlined,
  ExpandOutlined,
  CompressOutlined,
  InfoCircleOutlined,
  CodeOutlined,
  EnvironmentOutlined,
  BranchesOutlined,
  SettingOutlined,
  PartitionOutlined,
} from '@ant-design/icons';
import type { PipelineDetail, TaskYAML, TaskType, SubPipeline } from '@/types';
import { useAppStore } from '@/stores/appStore';

/** 任务类型颜色 */
const TASK_TYPE_COLOR: Record<TaskType, string> = {
  command: '#8c8c8c',
  invoke: '#1677ff',
  steps: '#722ed1',
  git: '#fa8c16',
  nexus: '#13c2c2',
  ssh: '#8c8c8c',
};

/** 任务类型标签 */
const TASK_TYPE_LABEL: Record<TaskType, string> = {
  command: '命令',
  invoke: '调用',
  steps: '步骤',
  git: 'Git',
  nexus: 'Nexus',
  ssh: 'SSH',
};

/** 推断任务类型 */
function inferTaskType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/** 根据 selectedNodeId 在 pipeline 中查找对应任务或子流水线 */
function findTask(
  pipeline: PipelineDetail | undefined,
  selectedNodeId: string | null,
): { task: TaskYAML; subName: string } | null {
  if (!pipeline || !selectedNodeId) return null;

  const subpipelines = pipeline.pipelines || [];
  for (const sub of subpipelines) {
    for (const task of sub.tasks) {
      if (`${sub.name}.${task.name}` === selectedNodeId) {
        return { task, subName: sub.name };
      }
    }
  }
  return null;
}

/** 根据 selectedNodeId 查找子流水线 */
function findSubpipeline(
  pipeline: PipelineDetail | undefined,
  selectedNodeId: string | null,
): SubPipeline | null {
  if (!pipeline || !selectedNodeId || !selectedNodeId.startsWith('__group__')) return null;

  const subName = selectedNodeId.replace('__group__', '');
  const subpipelines = pipeline.pipelines || [];
  return subpipelines.find((s) => s.name === subName) ?? null;
}

/** 基本 Tab 内容 */
function BasicTab({ task, subName }: { task: TaskYAML; subName: string }) {
  const taskType = inferTaskType(task);
  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      <div>
        <label className="text-xs text-gray-500 mb-1 block">名称</label>
        <Input value={task.name} readOnly size="small" />
      </div>
      <div>
        <label className="text-xs text-gray-500 mb-1 block">子流水线</label>
        <Input value={subName} readOnly size="small" />
      </div>
      <div>
        <label className="text-xs text-gray-500 mb-1 block">类型</label>
        <Tag color={TASK_TYPE_COLOR[taskType]}>{TASK_TYPE_LABEL[taskType]}</Tag>
      </div>
    </div>
  );
}

/** 源码 Tab 内容 */
function SourceTab({ task }: { task: TaskYAML }) {
  const taskType = inferTaskType(task);

  if (taskType === 'command') {
    return (
      <div className="flex flex-col gap-3 px-2 pt-2">
        {task.command && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">命令</label>
            <Input.TextArea value={task.command} readOnly size="small" autoSize={{ minRows: 2 }} />
          </div>
        )}
        {task.commands && task.commands.length > 0 && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">命令列表</label>
            <Input.TextArea
              value={task.commands.join('\n')}
              readOnly
              size="small"
              autoSize={{ minRows: 3 }}
            />
          </div>
        )}
      </div>
    );
  }

  if (taskType === 'invoke' && task.invoke) {
    return (
      <div className="flex flex-col gap-3 px-2 pt-2">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">调用任务</label>
          <Input value={task.invoke.task} readOnly size="small" />
        </div>
        {task.invoke.args && task.invoke.args.length > 0 && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">参数 (args)</label>
            <Input.TextArea
              value={JSON.stringify(task.invoke.args, null, 2)}
              readOnly
              size="small"
              autoSize={{ minRows: 2 }}
            />
          </div>
        )}
        {task.invoke.kwargs && Object.keys(task.invoke.kwargs).length > 0 && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">关键字参数 (kwargs)</label>
            <Input.TextArea
              value={JSON.stringify(task.invoke.kwargs, null, 2)}
              readOnly
              size="small"
              autoSize={{ minRows: 2 }}
            />
          </div>
        )}
      </div>
    );
  }

  if (taskType === 'steps' && task.steps) {
    return (
      <div className="flex flex-col gap-2 px-2 pt-2">
        {task.steps.map((step, i) => (
          <div key={i} className="border border-gray-200 rounded p-2">
            <div className="text-xs text-gray-500 mb-1">步骤 {i + 1}</div>
            <Input.TextArea value={step.run} readOnly size="small" autoSize={{ minRows: 1 }} />
            {step.cd && (
              <div className="mt-1">
                <span className="text-xs text-gray-400">cd: {step.cd}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (taskType === 'git' && task.git) {
    return (
      <div className="flex flex-col gap-3 px-2 pt-2">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">仓库</label>
          <Input value={task.git.repo} readOnly size="small" />
        </div>
        {task.git.ref && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">引用</label>
            <Input value={task.git.ref} readOnly size="small" />
          </div>
        )}
        <div>
          <label className="text-xs text-gray-500 mb-1 block">目标路径</label>
          <Input value={task.git.dest} readOnly size="small" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">深度</label>
          <Input value={String(task.git.depth)} readOnly size="small" />
        </div>
      </div>
    );
  }

  if (taskType === 'nexus' && task.nexus) {
    return (
      <div className="flex flex-col gap-3 px-2 pt-2">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">操作</label>
          <Input value={task.nexus.action} readOnly size="small" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">URL</label>
          <Input value={task.nexus.url} readOnly size="small" />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">仓库</label>
          <Input value={task.nexus.repository} readOnly size="small" />
        </div>
        {task.nexus.group_id && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Group ID</label>
            <Input value={task.nexus.group_id} readOnly size="small" />
          </div>
        )}
        {task.nexus.artifact_id && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Artifact ID</label>
            <Input value={task.nexus.artifact_id} readOnly size="small" />
          </div>
        )}
        {task.nexus.version && (
          <div>
            <label className="text-xs text-gray-500 mb-1 block">版本</label>
            <Input value={task.nexus.version} readOnly size="small" />
          </div>
        )}
      </div>
    );
  }

  return <div className="px-2 pt-2 text-xs text-gray-400">无源码信息</div>;
}

/** 环境变量 Tab 内容 */
function EnvTab({ task }: { task: TaskYAML }) {
  const entries = Object.entries(task.env || {});
  if (entries.length === 0) {
    return <div className="px-2 pt-2 text-xs text-gray-400">无环境变量</div>;
  }
  return (
    <Descriptions column={1} size="small" bordered className="mx-2 mt-2">
      {entries.map(([key, value]) => (
        <Descriptions.Item key={key} label={key}>
          <span className="text-xs font-mono">{String(value)}</span>
        </Descriptions.Item>
      ))}
    </Descriptions>
  );
}

/** 依赖 Tab 内容 */
function DepsTab({ task }: { task: TaskYAML }) {
  if (!task.depends_on || task.depends_on.length === 0) {
    return <div className="px-2 pt-2 text-xs text-gray-400">无依赖</div>;
  }
  return (
    <div className="flex flex-wrap gap-1 px-2 pt-2">
      {task.depends_on.map((dep) => (
        <Tag key={dep}>{dep}</Tag>
      ))}
    </div>
  );
}

/** 高级 Tab 内容 */
function AdvancedTab({ task }: { task: TaskYAML }) {
  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      {task.timeout != null && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">超时 (秒)</label>
          <Input value={String(task.timeout)} readOnly size="small" />
        </div>
      )}
      <div>
        <label className="text-xs text-gray-500 mb-1 block">重试次数</label>
        <Input value={String(task.retry)} readOnly size="small" />
      </div>
      {task.on_failure && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">失败处理</label>
          <Input value={task.on_failure} readOnly size="small" />
        </div>
      )}
      {task.when && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">执行条件 (when)</label>
          <Input.TextArea value={task.when} readOnly size="small" autoSize={{ minRows: 1 }} />
        </div>
      )}
      {task.cwd && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">工作目录</label>
          <Input value={task.cwd} readOnly size="small" />
        </div>
      )}
      {task.host && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">主机</label>
          <Input value={task.host} readOnly size="small" />
        </div>
      )}
      {task.credential && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">凭据</label>
          <Input value={task.credential} readOnly size="small" />
        </div>
      )}
    </div>
  );
}

interface PropertiesPanelProps {
  pipeline: PipelineDetail | undefined;
}

/** 子流水线信息面板 */
function SubpipelinePanel({ sub }: { sub: SubPipeline }) {
  const config = sub.config;
  const envEntries = Object.entries(config?.env || {});

  return (
    <div className="flex flex-col gap-3 px-2 pt-2">
      <div>
        <label className="text-xs text-gray-500 mb-1 block">名称</label>
        <Input value={sub.name} readOnly size="small" />
      </div>
      <div>
        <label className="text-xs text-gray-500 mb-1 block">任务数</label>
        <Input value={String(sub.tasks.length)} readOnly size="small" />
      </div>
      {sub.depends_on.length > 0 && (
        <div>
          <label className="text-xs text-gray-500 mb-1 block">依赖</label>
          <div className="flex flex-wrap gap-1">
            {sub.depends_on.map((dep) => (
              <Tag key={dep}>{dep}</Tag>
            ))}
          </div>
        </div>
      )}
      {config && (
        <>
          <div className="border-t border-gray-100 pt-2 mt-1">
            <label className="text-xs text-gray-500 mb-1 block">执行策略</label>
            <Input value={config.execution_strategy || 'sequential'} readOnly size="small" />
          </div>
          {config.on_failure && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">失败处理</label>
              <Input value={config.on_failure} readOnly size="small" />
            </div>
          )}
          {config.host && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">主机</label>
              <Input value={config.host} readOnly size="small" />
            </div>
          )}
          {config.credential && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">凭据</label>
              <Input value={config.credential} readOnly size="small" />
            </div>
          )}
          {config.timeout != null && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">超时 (秒)</label>
              <Input value={String(config.timeout)} readOnly size="small" />
            </div>
          )}
          {config.retry != null && config.retry > 0 && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">重试次数</label>
              <Input value={String(config.retry)} readOnly size="small" />
            </div>
          )}
          {config.max_parallel != null && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">最大并行数</label>
              <Input value={String(config.max_parallel)} readOnly size="small" />
            </div>
          )}
          {config.cwd && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">工作目录</label>
              <Input value={config.cwd} readOnly size="small" />
            </div>
          )}
        </>
      )}
      {envEntries.length > 0 && (
        <div className="border-t border-gray-100 pt-2 mt-1">
          <label className="text-xs text-gray-500 mb-2 block">
            <EnvironmentOutlined /> 环境变量
          </label>
          <Descriptions column={1} size="small" bordered>
            {envEntries.map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                <span className="text-xs font-mono">{String(value)}</span>
              </Descriptions.Item>
            ))}
          </Descriptions>
        </div>
      )}
    </div>
  );
}

/** 属性面板组件 */
export default function PropertiesPanel({ pipeline }: PropertiesPanelProps) {
  const selectedNodeId = useAppStore((s) => s.selectedNodeId);
  const panelMinimized = useAppStore((s) => s.panelMinimized);
  const panelMaximized = useAppStore((s) => s.panelMaximized);
  const setPanelMinimized = useAppStore((s) => s.setPanelMinimized);
  const setPanelMaximized = useAppStore((s) => s.setPanelMaximized);

  const found = useMemo(
    () => findTask(pipeline, selectedNodeId),
    [pipeline, selectedNodeId],
  );

  const foundSub = useMemo(
    () => findSubpipeline(pipeline, selectedNodeId),
    [pipeline, selectedNodeId],
  );

  // 最小化状态：显示图标条
  if (panelMinimized) {
    return (
      <div
        className="flex flex-col items-center py-3 gap-3 bg-white border-l border-gray-200"
        style={{ width: 40 }}
      >
        <Tooltip title="展开面板" placement="left">
          <Button
            type="text"
            size="small"
            icon={<ExpandOutlined />}
            onClick={() => setPanelMinimized(false)}
          />
        </Tooltip>
      </div>
    );
  }

  // 无选中任务或子流水线
  if (!found && !foundSub) {
    return (
      <div
        className="flex flex-col bg-white border-l border-gray-200"
        style={{ width: panelMaximized ? '70vw' : 420 }}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
          <span className="text-sm font-medium text-gray-600">属性面板</span>
          <div className="flex gap-1">
            <Tooltip title="最小化">
              <Button
                type="text"
                size="small"
                icon={<MinusOutlined />}
                onClick={() => setPanelMinimized(true)}
              />
            </Tooltip>
            <Tooltip title={panelMaximized ? '还原' : '最大化'}>
              <Button
                type="text"
                size="small"
                icon={panelMaximized ? <CompressOutlined /> : <ExpandOutlined />}
                onClick={() => setPanelMaximized(!panelMaximized)}
              />
            </Tooltip>
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center text-xs text-gray-400">
          点击节点查看属性
        </div>
      </div>
    );
  }

  // 子流水线选中
  if (foundSub && !found) {
    return (
      <div
        className="flex flex-col bg-white border-l border-gray-200"
        style={{ width: panelMaximized ? '70vw' : 420 }}
      >
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
          <span className="text-sm font-medium text-gray-800 truncate">
            <PartitionOutlined className="mr-1" />{foundSub.name}
          </span>
          <div className="flex gap-1 shrink-0">
            <Tooltip title="最小化">
              <Button
                type="text"
                size="small"
                icon={<MinusOutlined />}
                onClick={() => setPanelMinimized(true)}
              />
            </Tooltip>
            <Tooltip title={panelMaximized ? '还原' : '最大化'}>
              <Button
                type="text"
                size="small"
                icon={panelMaximized ? <CompressOutlined /> : <ExpandOutlined />}
                onClick={() => setPanelMaximized(!panelMaximized)}
              />
            </Tooltip>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <SubpipelinePanel sub={foundSub} />
        </div>
      </div>
    );
  }

  const { task, subName } = found!;

  return (
    <div
      className="flex flex-col bg-white border-l border-gray-200"
      style={{ width: panelMaximized ? '70vw' : 420 }}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
        <span className="text-sm font-medium text-gray-800 truncate">
          {task.name}
        </span>
        <div className="flex gap-1 shrink-0">
          <Tooltip title="最小化">
            <Button
              type="text"
              size="small"
              icon={<MinusOutlined />}
              onClick={() => setPanelMinimized(true)}
            />
          </Tooltip>
          <Tooltip title={panelMaximized ? '还原' : '最大化'}>
            <Button
              type="text"
              size="small"
              icon={panelMaximized ? <CompressOutlined /> : <ExpandOutlined />}
              onClick={() => setPanelMaximized(!panelMaximized)}
            />
          </Tooltip>
        </div>
      </div>

      {/* Tab 内容区 */}
      <div className="flex-1 overflow-y-auto">
        <Tabs
          size="small"
          items={[
            {
              key: 'basic',
              label: (
                <span>
                  <InfoCircleOutlined /> 基本
                </span>
              ),
              children: <BasicTab task={task} subName={subName} />,
            },
            {
              key: 'source',
              label: (
                <span>
                  <CodeOutlined /> 源码
                </span>
              ),
              children: <SourceTab task={task} />,
            },
            {
              key: 'env',
              label: (
                <span>
                  <EnvironmentOutlined /> 环境变量
                </span>
              ),
              children: <EnvTab task={task} />,
            },
            {
              key: 'deps',
              label: (
                <span>
                  <BranchesOutlined /> 依赖
                </span>
              ),
              children: <DepsTab task={task} />,
            },
            {
              key: 'advanced',
              label: (
                <span>
                  <SettingOutlined /> 高级
                </span>
              ),
              children: <AdvancedTab task={task} />,
            },
          ]}
        />
      </div>
    </div>
  );
}
