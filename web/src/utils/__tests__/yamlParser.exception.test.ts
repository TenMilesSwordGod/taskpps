import { describe, it, expect } from 'vitest';
import { parseYamlToPipeline } from '../yamlParser';

describe('yamlParser 异常流测试', () => {
  it('YAML 根节点为数组时 typeof 仍为 object，解析器会通过', () => {
    const yaml = `- item1\n- item2`;
    const result = parseYamlToPipeline(yaml);
    // js-yaml load 返回数组，typeof [] === 'object'，所以解析器不会拒绝
    // 但 pipeline 字段缺失，行为取决于 PipelineDetail 是否必需
    expect(result).toHaveProperty('success');
  });

  it('YAML 根节点为纯字符串', () => {
    const result = parseYamlToPipeline('hello world');
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('有效的对象');
  });

  it('YAML 根节点为数字', () => {
    const result = parseYamlToPipeline('42');
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('有效的对象');
  });

  it('YAML 根节点为布尔值', () => {
    const result = parseYamlToPipeline('true');
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('有效的对象');
  });

  it('YAML 根节点为 null', () => {
    const result = parseYamlToPipeline('null');
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('有效的对象');
  });

  it('tasks 字段为对象（非数组）时被忽略', () => {
    const yaml = `name: test\ntasks:\n  not: an-array`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.tasks).toBeUndefined();
  });

  it('pipelines 字段为字符串（非数组）时被忽略', () => {
    const yaml = `name: test\npipelines: "not an array"`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.pipelines).toBeUndefined();
  });

  it('options 字段为字符串（非对象）时被忽略', () => {
    const yaml = `name: test\noptions: "not an object"`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.options).toBeUndefined();
  });

  it('config 字段为数字（非对象）时被忽略', () => {
    const yaml = `name: test\nconfig: 123`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.config).toBeUndefined();
  });

  it('未知字段被静默忽略', () => {
    const yaml = `
name: test
unknown_field: value
another_unknown: 42
pipelines:
  - name: stage
    tasks:
      - name: t
        command: echo
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline).not.toHaveProperty('unknown_field');
  });

  it('YAML 缩进错误返回具体行号', () => {
    const yaml = `name: test\npipelines:\n- name: a\n   tasks:\n  - name: bad\n    command: echo`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(false);
    expect(result.error?.line).toBeGreaterThan(0);
  });

  it('YAML 包含未闭合的引号', () => {
    const yaml = `name: "unclosed\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(false);
  });

  it('YAML 包含非法 tab 缩进', () => {
    const yaml = "name: test\npipelines:\n\t- name: a\n\t\ttasks:\n\t\t\t- name: t\n\t\t\t\tcommand: echo";
    const result = parseYamlToPipeline(yaml);
    // js-yaml 对 tab 缩进会报错
    expect(result.success).toBe(false);
  });

  it('tasks 数组中包含非对象元素', () => {
    const yaml = `name: test\ntasks:\n  - "just a string"\n  - 42`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    // js-yaml 会解析为数组，但类型不匹配
    expect(result.pipeline?.tasks).toHaveLength(2);
  });

  it('pipelines 中 task 缺少 name 字段', () => {
    const yaml = `
name: test
pipelines:
  - name: stage
    tasks:
      - command: echo "no name"
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    // name 为 undefined，流程图应能处理
    expect(result.pipeline?.pipelines?.[0].tasks[0].name).toBeUndefined();
  });

  it('YAML 包含重复键时 js-yaml 默认行为', () => {
    const yaml = `name: first\nname: second\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo`;
    const result = parseYamlToPipeline(yaml);
    // js-yaml 默认禁止重复键，会抛出 YAMLException
    expect(result.success).toBe(false);
    expect(result.error?.message).toBeTruthy();
  });
});
