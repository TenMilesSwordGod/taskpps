import { Collapse, Form, Row, Col, Input, InputNumber, Select, Tooltip, Card } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { AgentWithConfig, ParamFieldDef, PipelineDetail } from '@/types';
import EnvEditor from './EnvEditor';
import AgentStatusDot from './AgentStatusDot';

// 注意(2026-09): dataKey 是 YAML/后端真实字段名，label 仅用于展示。
// retry/on_failure/execution_strategy 与后端 PipelineConfig 默认值保持一致（server/taskpps/schemas/pipeline.py），
// 否则 options 缺失时表单全空，用户无法知道实际生效值。
const CONFIG_FIELDS: ParamFieldDef[] = [
  { key: 'config_timeout', path: 'config.timeout', dataKey: 'timeout', label: 'timeout', type: 'number', placeholder: '超时秒数' },
  { key: 'config_retry', path: 'config.retry', dataKey: 'retry', label: 'retry', type: 'number', default: 0, placeholder: '重试次数' },
  // 注意(2026-09): 后端 Issue #106 已将 max_parallel 更名为 max_concurrent_runs，接口只返回新名
  { key: 'config_max_concurrent_runs', path: 'config.max_concurrent_runs', dataKey: 'max_concurrent_runs', label: 'max_concurrent_runs', type: 'number', placeholder: '最大并发' },
  { key: 'config_host', path: 'config.host', dataKey: 'host', label: 'host', type: 'host', placeholder: '执行主机' },
  {
    key: 'config_credential', path: 'config.credential', dataKey: 'credential', label: 'credential', type: 'string',
    placeholder: '凭证名称', hint: 'credentials/ 目录下定义的凭证标识，用于 SSH/Git/Nexus 认证',
  },
  { key: 'config_cwd', path: 'config.cwd', dataKey: 'cwd', label: 'cwd', type: 'string', placeholder: '工作目录' },
  { key: 'config_on_failure', path: 'config.on_failure', dataKey: 'on_failure', label: 'on_failure', type: 'select', default: 'fail', options: [{ label: 'fail', value: 'fail' }, { label: 'continue', value: 'continue' }] },
  // 注意(2026-09): label 展示为 strategy，真实字段名是 execution_strategy，两者不可混用
  { key: 'config_execution_strategy', path: 'config.execution_strategy', dataKey: 'execution_strategy', label: 'strategy', type: 'select', default: 'sequential', options: [{ label: 'sequential', value: 'sequential' }, { label: 'parallel', value: 'parallel' }] },
];

const TASK_FIELDS: ParamFieldDef[] = [
  { key: 'task_timeout', path: 'timeout', dataKey: 'timeout', label: 'timeout', type: 'number', placeholder: '超时秒数' },
  { key: 'task_retry', path: 'retry', dataKey: 'retry', label: 'retry', type: 'number', placeholder: '重试次数' },
  { key: 'task_host', path: 'host', dataKey: 'host', label: 'host', type: 'host', placeholder: '执行主机' },
  {
    key: 'task_credential', path: 'credential', dataKey: 'credential', label: 'credential', type: 'string',
    placeholder: '凭证名称', hint: '引用 credentials/ 目录下定义的凭证',
  },
  { key: 'task_cwd', path: 'cwd', dataKey: 'cwd', label: 'cwd', type: 'string', placeholder: '工作目录' },
  { key: 'task_on_failure', path: 'on_failure', dataKey: 'on_failure', label: 'on_failure', type: 'select', options: [{ label: 'fail', value: 'fail' }, { label: 'continue', value: 'continue' }] },
  {
    key: 'task_when', path: 'when', dataKey: 'when', label: 'when', type: 'string', placeholder: '${{ env.xxx == "prod" }}',
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
    // 注意(2026-09): 按 dataKey 读真实字段；options 缺失时用 default 回填有效默认值。
    // 只有 default 为 undefined 的字段（timeout/host 等）才保持空，空表示"不覆盖"。
    initial[field.key] = toFormValue(config[field.dataKey] ?? field.default, field.type);
  }
  initial['config_env'] = config['env'] || {};

  const tasks = extractTasks(pipelineData);
  for (const task of tasks) {
    for (const field of TASK_FIELDS) {
      const taskKey = `task_${task.name}_${field.label}`;
      // 注意(2026-09): task 层不做默认值回填——on_failure 为 None 表示继承 pipeline，
      // 若在此伪造默认值会改变"空 = 继承/不覆盖"的语义
      initial[taskKey] = toFormValue(task[field.dataKey], field.type);
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
    // 注意(2026-09): 比较基准是"有效值"（已有值 ?? 默认值），
    // 否则回填的默认值会被误判为改动，提交出多余的覆盖项
    const currentVal = toFormValue(config[field.dataKey] ?? field.default, field.type);
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
      const currentVal = toFormValue(task[field.dataKey], field.type);
      const newVal = formValues[taskKey];
      const parsed = parseValue(newVal, field.type);

      if (parsed === undefined || parsed === null || parsed === '') continue;
      if (JSON.stringify(parsed) === JSON.stringify(parseValue(currentVal, field.type))) continue;

      params[`tasks["${task.name}"].${field.dataKey}`] = parsed;
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
