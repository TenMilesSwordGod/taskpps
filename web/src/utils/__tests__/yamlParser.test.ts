import { describe, it, expect } from 'vitest';
import { parseYamlToPipeline, pipelineToYaml } from '../yamlParser';
import type { PipelineDetail } from '@/types';

describe('parseYamlToPipeline', () => {
  it('解析有效的简单 pipeline YAML', () => {
    const yaml = `
name: test-pipeline
pipelines:
  - name: build
    tasks:
      - name: compile
        command: echo "hello"
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toBe('test-pipeline');
    expect(result.pipeline?.pipelines).toHaveLength(1);
    expect(result.pipeline?.pipelines?.[0].name).toBe('build');
    expect(result.pipeline?.pipelines?.[0].tasks).toHaveLength(1);
    expect(result.pipeline?.pipelines?.[0].tasks[0].name).toBe('compile');
  });

  it('解析带 depends_on 的 pipeline', () => {
    const yaml = `
name: multi-stage
pipelines:
  - name: prepare
    tasks:
      - name: lint
        command: ruff check .
  - name: build
    depends_on:
      - prepare
    tasks:
      - name: compile
        command: make build
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.pipelines).toHaveLength(2);
    expect(result.pipeline?.pipelines?.[1].depends_on).toEqual(['prepare']);
  });

  it('空 YAML 返回错误', () => {
    const result = parseYamlToPipeline('');
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('为空');
  });

  it('无效 YAML 语法返回错误（含行号）', () => {
    const yaml = `
name: broken
pipelines:
  - name: build
    tasks:
      - name: bad
        command: echo
      invalid: [unclosed
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(false);
    expect(result.error?.message).toBeTruthy();
    expect(result.error?.line).toBeGreaterThan(0);
  });

  it('解析含 config 和 options 的 pipeline', () => {
    const yaml = `
name: with-config
options:
  execution_strategy: parallel
pipelines:
  - name: deploy
    config:
      execution_strategy: sequential
      timeout: 300
    tasks:
      - name: push
        command: git push
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.options?.execution_strategy).toBe('parallel');
    expect(result.pipeline?.pipelines?.[0].config?.execution_strategy).toBe('sequential');
  });

  it('解析含 post 配置的 pipeline', () => {
    const yaml = `
name: with-post
pipelines:
  - name: build
    tasks:
      - name: compile
        command: make
        post:
          on_fail:
            - name: notify-fail
              command: echo "failed"
          on_success:
            - name: notify-ok
              command: echo "ok"
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    const task = result.pipeline?.pipelines?.[0].tasks[0];
    expect(task?.post?.on_fail).toHaveLength(1);
    expect(task?.post?.on_success).toHaveLength(1);
  });

  it('处理只有 tasks 没有 pipelines 的情况', () => {
    const yaml = `
name: flat
tasks:
  - name: run
    command: echo hello
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.tasks).toHaveLength(1);
    expect(result.pipeline?.pipelines).toBeUndefined();
  });
});

describe('pipelineToYaml', () => {
  it('序列化简单 pipeline', () => {
    const pipeline: PipelineDetail = {
      name: 'test',
      pipelines: [
        {
          name: 'build',
          depends_on: [],
          tasks: [{ name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    };
    const yaml = pipelineToYaml(pipeline);
    expect(yaml).toContain('name: test');
    expect(yaml).toContain('compile');
    expect(yaml).toContain('make');
  });

  it('round-trip: pipeline -> yaml -> pipeline 保持一致', () => {
    const original: PipelineDetail = {
      name: 'roundtrip',
      pipelines: [
        {
          name: 'stage1',
          depends_on: [],
          tasks: [
            { name: 'task-a', command: 'echo a', env: {}, retry: 0, depends_on: [] },
            { name: 'task-b', command: 'echo b', env: {}, retry: 0, depends_on: ['task-a'] },
          ],
        },
      ],
    };
    const yamlStr = pipelineToYaml(original);
    const result = parseYamlToPipeline(yamlStr);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toBe('roundtrip');
    expect(result.pipeline?.pipelines).toHaveLength(1);
    expect(result.pipeline?.pipelines?.[0].tasks).toHaveLength(2);
    expect(result.pipeline?.pipelines?.[0].tasks[1].depends_on).toEqual(['task-a']);
  });
});
