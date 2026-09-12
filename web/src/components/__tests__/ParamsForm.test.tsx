import { describe, it, expect } from 'vitest';
import { buildInitialValues, buildOverrideParams } from '../ParamsForm';
import type { PipelineDetail } from '@/types';

// Issue 回归：运行弹窗必须按 YAML 真实字段名（dataKey）读写，
// 展示名（label）只用于 UI，不能参与数据映射。

function makeTask(overrides: Record<string, unknown> = {}) {
  return {
    name: 'hello',
    command: 'echo hi',
    env: {},
    retry: 0,
    depends_on: [],
    ...overrides,
  };
}

// options 缺失是常见场景：定义 JSON 里 options=null，表达式默认值不能被丢掉
const pipelineNoOptions: PipelineDetail = {
  name: 'demo',
  options: null,
  tasks: [makeTask()],
};

// options 完整时，已有值必须优先于默认值展示
const pipelineWithOptions: PipelineDetail = {
  name: 'demo',
  options: {
    host: 'agent-1',
    credential: 'deploy-cred',
    env: { A: '1' },
    timeout: 60,
    retry: 2,
    on_failure: 'continue',
    execution_strategy: 'parallel',
    max_concurrent_runs: 4,
    cwd: '/srv/app',
  },
  tasks: [makeTask()],
};

describe('ParamsForm 参数映射', () => {
  describe('buildInitialValues', () => {
    it('options 缺失时回填 pipeline 有效默认值，未设置项保持空', () => {
      const initial = buildInitialValues(pipelineNoOptions);

      expect(initial.config_retry).toBe(0);
      expect(initial.config_on_failure).toBe('fail');
      expect(initial.config_execution_strategy).toBe('sequential');
      expect(initial.config_env).toEqual({});

      // 默认值为 None 的字段不应伪造值（空 = 不覆盖）
      expect(initial.config_timeout).toBeUndefined();
      expect(initial.config_host).toBeUndefined();
      expect(initial.config_credential).toBeUndefined();
      expect(initial.config_cwd).toBeUndefined();
      expect(initial.config_max_concurrent_runs).toBeUndefined();
    });

    it('options 已有值时正确回填 strategy 与 max_concurrent_runs', () => {
      const initial = buildInitialValues(pipelineWithOptions);

      expect(initial.config_execution_strategy).toBe('parallel');
      expect(initial.config_max_concurrent_runs).toBe(4);
      expect(initial.config_host).toBe('agent-1');
      expect(initial.config_credential).toBe('deploy-cred');
      expect(initial.config_timeout).toBe(60);
      expect(initial.config_retry).toBe(2);
      expect(initial.config_on_failure).toBe('continue');
      expect(initial.config_cwd).toBe('/srv/app');
      expect(initial.config_env).toEqual({ A: '1' });
    });

    it('task 层字段按 dataKey 回填', () => {
      const pipeline: PipelineDetail = {
        name: 'demo',
        tasks: [makeTask({ timeout: 30, host: 'agent-2', when: 'true' })],
      };
      const initial = buildInitialValues(pipeline);

      expect(initial.task_hello_timeout).toBe(30);
      expect(initial.task_hello_host).toBe('agent-2');
      expect(initial.task_hello_when).toBe('true');
      expect(initial.task_hello_retry).toBe(0);
      expect(initial.task_hello_on_failure).toBeUndefined();
    });
  });

  describe('buildOverrideParams', () => {
    it('原样提交默认值时不应产生任何覆盖', () => {
      const params = buildOverrideParams(
        buildInitialValues(pipelineNoOptions),
        pipelineNoOptions,
      );

      expect(params).toEqual({});
    });

    it('原样提交已有值时不应产生任何覆盖', () => {
      const params = buildOverrideParams(
        buildInitialValues(pipelineWithOptions),
        pipelineWithOptions,
      );

      expect(params).toEqual({});
    });

    it('修改 strategy / max_concurrent_runs 输出后端合法路径', () => {
      const values = {
        ...buildInitialValues(pipelineNoOptions),
        config_execution_strategy: 'parallel',
        config_max_concurrent_runs: 4,
      };
      const params = buildOverrideParams(values, pipelineNoOptions);

      expect(params).toEqual({
        'config.execution_strategy': 'parallel',
        'config.max_concurrent_runs': 4,
      });
    });

    it('修改 on_failure / retry 仅输出被改动项', () => {
      const values = {
        ...buildInitialValues(pipelineNoOptions),
        config_on_failure: 'continue',
        config_retry: 3,
      };
      const params = buildOverrideParams(values, pipelineNoOptions);

      expect(params).toEqual({
        'config.on_failure': 'continue',
        'config.retry': 3,
      });
    });

    it('清空默认值表示不覆盖，而不是回落默认值', () => {
      const values = {
        ...buildInitialValues(pipelineNoOptions),
        config_on_failure: undefined,
        config_execution_strategy: undefined,
      };
      const params = buildOverrideParams(values, pipelineNoOptions);

      expect(params).toEqual({});
    });

    it('task 覆盖输出 tasks["name"].field 路径', () => {
      const values = {
        ...buildInitialValues(pipelineNoOptions),
        task_hello_timeout: 99,
        task_hello_on_failure: 'continue',
      };
      const params = buildOverrideParams(values, pipelineNoOptions);

      expect(params).toEqual({
        'tasks["hello"].timeout': 99,
        'tasks["hello"].on_failure': 'continue',
      });
    });
  });
});
