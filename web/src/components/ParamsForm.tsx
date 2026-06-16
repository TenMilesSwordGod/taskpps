import { Collapse, Form, Row, Col, Input, InputNumber, Select, Tooltip, Card } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { AgentWithConfig, ParamFieldDef, PipelineDetail } from '@/types';
import EnvEditor from './EnvEditor';
import AgentStatusDot from './AgentStatusDot';

const CONFIG_FIELDS: ParamFieldDef[] = [
  { key: 'config_timeout', path: 'config.timeout', label: 'timeout', type: 'number', placeholder: '超时秒数' },
  { key: 'config_retry', path: 'config.retry', label: 'retry', type: 'number', placeholder: '重试次数' },
  { key: 'config_max_parallel', path: 'config.max_parallel', label: 'max_parallel', type: 'number', placeholder: '最大并发' },
  { key: 'config_host', path: 'config.host', label: 'host', type: 'host', placeholder: '执行主机' },
  {
    key: 'config_credential', path: 'config.credential', label: 'credential', type: 'string',
    placeholder: '凭证名称', hint: 'credentials/ 目录下定义的凭证标识，用于 SSH/Git/Nexus 认证',
  },
  { key: 'config_cwd', path: 'config.cwd', label: 'cwd', type: 'string', placeholder: '工作目录' },
  { key: 'config_on_failure', path: 'config.on_failure', label: 'on_failure', type: 'select', options: [{ label: 'fail', value: 'fail' }, { label: 'continue', value: 'continue' }] },
  { key: 'config_execution_strategy', path: 'config.execution_strategy', label: 'strategy', type: 'select', options: [{ label: 'sequential', value: 'sequential' }, { label: 'parallel', value: 'parallel' }] },
];

const TASK_FIELDS: ParamFieldDef[] = [
  { key: 'task_timeout', path: 'timeout', label: 'timeout', type: 'number', placeholder: '超时秒数' },
  { key: 'task_retry', path: 'retry', label: 'retry', type: 'number', placeholder: '重试次数' },
  { key: 'task_host', path: 'host', label: 'host', type: 'host', placeholder: '执行主机' },
  {
    key: 'task_credential', path: 'credential', label: 'credential', type: 'string',
    placeholder: '凭证名称', hint: '引用 credentials/ 目录下定义的凭证',
  },
  { key: 'task_cwd', path: 'cwd', label: 'cwd', type: 'string', placeholder: '工作目录' },
  { key: 'task_on_failure', path: 'on_failure', label: 'on_failure', type: 'select', options: [{ label: 'fail', value: 'fail' }, { label: 'continue', value: 'continue' }] },
  {
    key: 'task_when', path: 'when', label: 'when', type: 'string', placeholder: '${{ env.xxx == "prod" }}',
    hint: '条件表达式，支持 ${{ env.xxx }}、${{ task.xxx.output }} 等变量引用',
  },
];

function parseValue(val: unknown, type: string): unknown {
  if (val === undefined || val === null || val === '') return val;
  if (type === 'number') {
    const n = Number(val);
    return Number.isNaN(n) ? val : n;
  }
  if (type === 'json') {
    try { return JSON.parse(val as string); } catch { return val; }
  }
  return val;
}

function toFormValue(val: unknown, type: string): unknown {
  if (type === 'json' && typeof val === 'object' && val !== null) {
    return JSON.stringify(val, null, 2);
  }
  return val;
}

function extractTasks(pipelineData: PipelineDetail): Array<Record<string, unknown>> {
  if (pipelineData.tasks && pipelineData.tasks.length > 0) {
    return pipelineData.tasks as unknown as Array<Record<string, unknown>>;
  }
  if (pipelineData.pipelines && pipelineData.pipelines.length > 0) {
    return pipelineData.pipelines[0].tasks as unknown as Array<Record<string, unknown>>;
  }
  return [];
}

function getConfig(pipelineData: PipelineDetail): Record<string, unknown> {
  return (pipelineData.options || pipelineData.config || {}) as Record<string, unknown>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildInitialValues(pipelineData: PipelineDetail): Record<string, unknown> {
  const initial: Record<string, unknown> = {};
  const config = getConfig(pipelineData);

  for (const field of CONFIG_FIELDS) {
    if (field.type === 'host') {
      initial[field.key] = config[field.label];
    } else {
      initial[field.key] = toFormValue(config[field.label], field.type);
    }
  }
  initial['config_env'] = config['env'] || {};

  const tasks = extractTasks(pipelineData);
  for (const task of tasks) {
    for (const field of TASK_FIELDS) {
      const taskKey = `task_${task.name}_${field.label}`;
      initial[taskKey] = toFormValue(task[field.label], field.type);
    }
    initial[`task_${task.name}_env`] = task['env'] || {};
  }

  return initial;
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildOverrideParams(
  formValues: Record<string, unknown>,
  pipelineData: PipelineDetail,
): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  const config = getConfig(pipelineData);

  for (const field of CONFIG_FIELDS) {
    const currentVal = toFormValue(config[field.label], field.type);
    const newVal = formValues[field.key];
    const parsed = parseValue(newVal, field.type);

    if (parsed === undefined || parsed === null || parsed === '') continue;
    if (JSON.stringify(parsed) === JSON.stringify(parseValue(currentVal, field.type))) continue;

    params[field.path] = parsed;
  }

  const envVal = (formValues['config_env'] || {}) as Record<string, string>;
  const currentEnv = (config['env'] || {}) as Record<string, string>;
  if (JSON.stringify(envVal) !== JSON.stringify(currentEnv)) {
    params['config.env'] = envVal;
  }

  const tasks = extractTasks(pipelineData);
  for (const task of tasks) {
    for (const field of TASK_FIELDS) {
      const taskKey = `task_${task.name}_${field.label}`;
      const currentVal = toFormValue(task[field.label], field.type);
      const newVal = formValues[taskKey];
      const parsed = parseValue(newVal, field.type);

      if (parsed === undefined || parsed === null || parsed === '') continue;
      if (JSON.stringify(parsed) === JSON.stringify(parseValue(currentVal, field.type))) continue;

      params[`tasks["${task.name}"].${field.label}`] = parsed;
    }

    const taskEnvVal = (formValues[`task_${task.name}_env`] || {}) as Record<string, string>;
    const taskCurrentEnv = (task['env'] || {}) as Record<string, string>;
    if (JSON.stringify(taskEnvVal) !== JSON.stringify(taskCurrentEnv)) {
      params[`tasks["${task.name}"].env`] = taskEnvVal;
    }
  }

  return params;
}

function renderFieldLabel(field: ParamFieldDef) {
  if (!field.hint) return field.label;
  return (
    <span>
      {field.label}
      <Tooltip title={<span style={{ fontSize: 12 }}>{field.hint}</span>}>
        <QuestionCircleOutlined style={{ marginLeft: 4, color: '#9ca3af', fontSize: 11, cursor: 'help' }} />
      </Tooltip>
    </span>
  );
}

function renderField(
  field: ParamFieldDef,
  agents?: AgentWithConfig[],
) {
  switch (field.type) {
    case 'number':
      return <InputNumber size="small" style={{ width: '100%' }} placeholder={field.placeholder} />;
    case 'select':
      return <Select size="small" placeholder={field.placeholder} options={field.options} allowClear />;
    case 'host':
      return (
        <Select
          size="small"
          placeholder={field.placeholder}
          allowClear
          showSearch
          optionFilterProp="label"
        >
          {(agents || []).map((a) => (
            <Select.Option key={a.agent_id} value={a.agent_id} label={a.agent_id}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AgentStatusDot connected={a.connected} netStatus={a.net_status} />
                <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{a.agent_id}</span>
                <span style={{ color: '#9ca3af', fontSize: 11 }}>{a.host}</span>
              </div>
            </Select.Option>
          ))}
        </Select>
      );
    default:
      return <Input size="small" placeholder={field.placeholder} />;
  }
}

interface ParamsFormProps {
  pipelineData: PipelineDetail;
  agents?: AgentWithConfig[];
}

export default function ParamsForm({ pipelineData, agents }: ParamsFormProps) {
  const tasks = extractTasks(pipelineData);

  return (
    <>
      <Card
        size="small"
        title="Pipeline 参数"
        styles={{ header: { fontSize: 13, fontWeight: 600 }, body: { padding: '12px 16px' } }}
      >
        <Row gutter={[16, 8]}>
          {CONFIG_FIELDS.map((field) => (
            <Col key={field.key} span={8}>
              <Form.Item
                name={field.key}
                label={renderFieldLabel(field)}
                style={{ marginBottom: 0 }}
              >
                {renderField(field, agents)}
              </Form.Item>
            </Col>
          ))}
        </Row>
        <div style={{ marginTop: 12 }}>
          <Form.Item name="config_env" style={{ marginBottom: 0 }}>
            <EnvEditor />
          </Form.Item>
        </div>
      </Card>

      {tasks.length > 0 && (
        <Collapse
          size="small"
          style={{ marginTop: 8 }}
          items={tasks.map((task) => ({
            key: task.name as string,
            label: <span style={{ fontSize: 13, fontWeight: 600 }}>{task.name as string}</span>,
            children: (
              <>
                <Row gutter={[16, 8]}>
                  {TASK_FIELDS.map((field) => (
                    <Col key={`task_${task.name}_${field.label}`} span={8}>
                      <Form.Item
                        name={`task_${task.name}_${field.label}`}
                        label={renderFieldLabel(field)}
                        style={{ marginBottom: 0 }}
                      >
                        {renderField(field, agents)}
                      </Form.Item>
                    </Col>
                  ))}
                </Row>
                <div style={{ marginTop: 12 }}>
                  <Form.Item name={`task_${task.name}_env`} style={{ marginBottom: 0 }}>
                    <EnvEditor />
                  </Form.Item>
                </div>
              </>
            ),
          }))}
        />
      )}
    </>
  );
}
