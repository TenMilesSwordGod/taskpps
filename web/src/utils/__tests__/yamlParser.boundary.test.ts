import { describe, it, expect } from 'vitest';
import { parseYamlToPipeline, pipelineToYaml } from '../yamlParser';
import type { PipelineDetail } from '@/types';

describe('yamlParser 边界值测试', () => {
  it('仅空白字符串返回错误', () => {
    const result = parseYamlToPipeline('   \n  \n  ');
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('为空');
  });

  it('仅 tab 和换行返回错误', () => {
    const result = parseYamlToPipeline('\t\n\r\n');
    expect(result.success).toBe(false);
  });

  it('超长 YAML 文本（1000+ 行）正常解析', () => {
    const tasks = Array.from({ length: 1000 }, (_, i) => `        - name: task-${i}\n          command: echo ${i}`).join('\n');
    const yaml = `name: mega-pipeline\npipelines:\n  - name: stage\n    tasks:\n${tasks}`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.pipelines?.[0].tasks).toHaveLength(1000);
  });

  it('Unicode 名称（中文、日文、emoji）正常解析', () => {
    const yaml = `
name: 测试流水线-🚀
pipelines:
  - name: 构建阶段
    tasks:
      - name: 编译_📦
        command: echo "こんにちは"
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toBe('测试流水线-🚀');
    expect(result.pipeline?.pipelines?.[0].name).toBe('构建阶段');
    expect(result.pipeline?.pipelines?.[0].tasks[0].name).toBe('编译_📦');
  });

  it('特殊字符在名称和命令中', () => {
    const yaml = `
name: "special-chars!@#\$%^&*()"
pipelines:
  - name: "stage with spaces & symbols"
    tasks:
      - name: "task<>{}|"
        command: "echo 'hello world' && ls -la || exit 1"
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toContain('special-chars');
  });

  it('name 字段为空字符串时回退为 unnamed（String falsy）', () => {
    const yaml = `name: ""\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    // String('' || 'unnamed') → 'unnamed'，因为空字符串是 falsy
    expect(result.pipeline?.name).toBe('unnamed');
  });

  it('name 字段为数字类型时转为字符串', () => {
    const yaml = `name: 12345\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toBe('12345');
  });

  it('超深嵌套结构（5 层以上）正常解析', () => {
    const yaml = `
name: deep
options:
  level1:
    level2:
      level3:
        level4:
          level5:
            value: deep-value
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
  });

  it('单行超长值（10000+ 字符）', () => {
    const longValue = 'x'.repeat(10000);
    const yaml = `name: test\ntasks:\n  - name: t\n    command: echo "${longValue}"`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
  });

  it('pipelineToYaml 空 pipelines 数组', () => {
    const pipeline: PipelineDetail = { name: 'empty', pipelines: [] };
    const yaml = pipelineToYaml(pipeline);
    expect(yaml).toContain('name: empty');
  });

  it('pipelineToYaml tasks 为 null', () => {
    const pipeline: PipelineDetail = { name: 'test', tasks: null };
    const yaml = pipelineToYaml(pipeline);
    expect(yaml).toContain('name: test');
    expect(yaml).not.toContain('tasks');
  });

  it('pipelineToYaml 所有可选字段均存在', () => {
    const pipeline: PipelineDetail = {
      name: 'full',
      options: { execution_strategy: 'parallel' },
      config: { timeout: 300 },
      tasks: [{ name: 't', command: 'echo', env: {}, retry: 0, depends_on: [] }],
      pipelines: [{ name: 'p', depends_on: [], tasks: [{ name: 't2', command: 'echo2', env: {}, retry: 0, depends_on: [] }] }],
    };
    const yaml = pipelineToYaml(pipeline);
    expect(yaml).toContain('options');
    expect(yaml).toContain('config');
    expect(yaml).toContain('tasks');
    expect(yaml).toContain('pipelines');
  });
});
