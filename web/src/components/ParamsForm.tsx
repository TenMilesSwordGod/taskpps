import { Collapse, Form, Input, InputNumber, Select } from 'antd';
import type { ParamFieldDef, PipelineDetail } from '@/types';

const CONFIG_PARAM_FIELDS: ParamFieldDef[] = [
  { key: 'config_timeout', path: 'config.timeout', label: 'timeout', type: 'number', placeholder: '超时秒数' },
  { key: 'config_retry', path: 'config.retry', label: 'retry', type: 'number', placeholder: '重试次数' },
  { key: 'config_max_parallel', path: 'config.max_parallel', label: 'max_parallel', type: 'number', placeholder: '最大并发数' },
  { key: 'config_host', path: 'config.host', label: 'host', type: 'string', placeholder: '执行主机' },
  { key: 'config_credential', path: 'config.credential', label: 'credential', type: 'string', placeholder: '凭证名称' },
  { key: 'config_cwd', path: 'config.cwd', label: 'cwd', type: 'string', placeholder: '工作目录' },
  { key: 'config_on_failure', path: 'config.on_failure', label: 'on_failure', type: 'select', options: [{ label: 'fail', value: 'fail' }, { label: 'continue', value: 'continue' }] },
  { key: 'config_execution_strategy', path: 'config.execution_strategy', label: 'execution_strategy', type: 'select', options: [{ label: 'sequential', value: 'sequential' }, { label: 'parallel', value: 'parallel' }] },
  { key: 'config_env', path: 'config.env', label: 'env', type: 'json', placeholder: '{"KEY": "value"}' },
];

const TASK_PARAM_FIELDS: ParamFieldDef[] = [
  { key: 'task_timeout', path: 'timeout', label: 'timeout', type: 'number', placeholder: '超时秒数' },
  { key: 'task_retry', path: 'retry', label: 'retry', type: 'number', placeholder: '重试次数' },
  { key: 'task_host', path: 'host', label: 'host', type: 'string', placeholder: '执行主机' },
  { key: 'task_credential', path: 'credential', label: 'credential', type: 'string', placeholder: '凭证名称' },
  { key: 'task_cwd', path: 'cwd', label: 'cwd', type: 'string', placeholder: '工作目录' },
  { key: 'task_on_failure', path: 'on_failure', label: 'on_failure', type: 'select', options: [{ label: 'fail', value: 'fail' }, { label: 'continue', value: 'continue' }] },
  { key: 'task_when', path: 'when', label: 'when', type: 'string', placeholder: '条件表达式' },
  { key: 'task_env', path: 'env', label: 'env', type: 'json', placeholder: '{"KEY": "value"}' },
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

  for (const field of CONFIG_PARAM_FIELDS) {
    initial[field.key] = toFormValue(config[field.label], field.type);
  }

  const tasks = extractTasks(pipelineData);
  for (const task of tasks) {
    for (const field of TASK_PARAM_FIELDS) {
      const taskKey = `task_${task.name}_${field.label}`;
      initial[taskKey] = toFormValue(task[field.label], field.type);
    }
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

  for (const field of CONFIG_PARAM_FIELDS) {
    const currentVal = toFormValue(config[field.label], field.type);
    const newVal = formValues[field.key];
    const parsed = parseValue(newVal, field.type);

    if (parsed === undefined || parsed === null || parsed === '') continue;
    if (JSON.stringify(parsed) === JSON.stringify(parseValue(currentVal, field.type))) continue;

    params[field.path] = parsed;
  }

  const tasks = extractTasks(pipelineData);
  for (const task of tasks) {
    for (const field of TASK_PARAM_FIELDS) {
      const taskKey = `task_${task.name}_${field.label}`;
      const currentVal = toFormValue(task[field.label], field.type);
      const newVal = formValues[taskKey];
      const parsed = parseValue(newVal, field.type);

      if (parsed === undefined || parsed === null || parsed === '') continue;
      if (JSON.stringify(parsed) === JSON.stringify(parseValue(currentVal, field.type))) continue;

      params[`tasks["${task.name}"].${field.label}`] = parsed;
    }
  }

  return params;
}

function renderField(field: ParamFieldDef) {
  switch (field.type) {
    case 'number':
      return <InputNumber style={{ width: '100%' }} placeholder={field.placeholder} />;
    case 'select':
      return <Select placeholder={field.placeholder} options={field.options} allowClear />;
    case 'json':
      return <Input.TextArea rows={3} placeholder={field.placeholder || '{"KEY": "value"}'} />;
    default:
      return <Input placeholder={field.placeholder} />;
  }
}

interface ParamsFormProps {
  pipelineData: PipelineDetail;
}

export default function ParamsForm({ pipelineData }: ParamsFormProps) {
  const tasks = extractTasks(pipelineData);

  return (
    <>
      <Collapse
        size="small"
        defaultActiveKey={['config']}
        items={[{
          key: 'config',
          label: 'Pipeline 级参数',
          children: (
            <>
              {CONFIG_PARAM_FIELDS.map((field) => (
                <Form.Item key={field.key} name={field.key} label={field.label}>
                  {renderField(field)}
                </Form.Item>
              ))}
            </>
          ),
        }]}
      />

      {tasks.length > 0 && (
        <Collapse
          size="small"
          style={{ marginTop: 8 }}
          items={tasks.map((task) => ({
            key: task.name as string,
            label: task.name as string,
            children: (
              <>
                {TASK_PARAM_FIELDS.map((field) => (
                  <Form.Item
                    key={`task_${task.name}_${field.label}`}
                    name={`task_${task.name}_${field.label}`}
                    label={field.label}
                  >
                    {renderField(field)}
                  </Form.Item>
                ))}
              </>
            ),
          }))}
        />
      )}
    </>
  );
}
