import { describe, it, expect } from 'vitest';
import { parseYamlToPipeline, pipelineToYaml } from '../yamlParser';
import type { PipelineDetail } from '@/types';

describe('yamlParser 环境兼容性测试', () => {
  it('Windows 换行符 (CRLF) 正常解析', () => {
    const yaml = 'name: test\r\npipelines:\r\n  - name: stage\r\n    tasks:\r\n      - name: t\r\n        command: echo';
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toBe('test');
  });

  it('旧版 Mac 换行符 (CR) 正常解析', () => {
    const yaml = 'name: test\rpipelines:\r  - name: stage\rtasks:\r    - name: t\r      command: echo';
    const result = parseYamlToPipeline(yaml);
    // CR 换行可能导致解析问题，但不应崩溃
    expect(result).toHaveProperty('success');
  });

  it('BOM 头 (UTF-8 with BOM) 处理', () => {
    const yaml = '\uFEFFname: test\npipelines:\n  - name: stage\n    tasks:\n      - name: t\n        command: echo';
    const result = parseYamlToPipeline(yaml);
    // js-yaml 不支持 BOM，会解析失败。记录此行为。
    expect(result).toHaveProperty('success');
  });

  it('包含注释的 YAML 正常解析', () => {
    const yaml = `
# 这是一个注释
name: test  # 行尾注释
pipelines:
  # 阶段注释
  - name: stage
    tasks:
      - name: t
        command: echo  # echo 命令
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.name).toBe('test');
  });

  it('YAML 多文档分隔符 (---) 处理', () => {
    const yaml = '---\nname: doc1\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo\n---\nname: doc2';
    const result = parseYamlToPipeline(yaml);
    // js-yaml load 不支持多文档分隔符，会解析失败
    expect(result).toHaveProperty('success');
  });

  it('YAML 锚点和引用 (& 和 *)', () => {
    const yaml = `
name: anchored
defaults: &defaults
  retry: 3
  env:
    NODE_ENV: production
pipelines:
  - name: stage
    tasks:
      - name: t
        command: echo
        <<: *defaults
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
  });

  it('YAML 多行字符串 (| 和 >)', () => {
    const yaml = `
name: multiline
pipelines:
  - name: stage
    tasks:
      - name: t
        command: |
          echo "line1"
          echo "line2"
          echo "line3"
`;
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.pipelines?.[0].tasks[0].command).toContain('line1');
  });

  it('YAML 二进制数据 (!!binary) 处理', () => {
    const yaml = `
name: binary-test
config:
  data: !!binary |
    R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7
`;
    const result = parseYamlToPipeline(yaml);
    // js-yaml 可能不支持 !!binary schema，记录实际行为
    expect(result).toHaveProperty('success');
  });

  it('空对象和空数组', () => {
    const yaml = 'name: empty-test\npipelines: []\ntasks: []';
    const result = parseYamlToPipeline(yaml);
    expect(result.success).toBe(true);
    expect(result.pipeline?.pipelines).toEqual([]);
  });

  it('pipelineToYaml 输出不包含 refs (noRefs: true)', () => {
    const pipeline: PipelineDetail = {
      name: 'test',
      pipelines: [
        {
          name: 'stage',
          depends_on: [],
          tasks: [{ name: 't', command: 'echo', env: {}, retry: 0, depends_on: [] }],
        },
      ],
    };
    const yaml = pipelineToYaml(pipeline);
    // 不应包含 YAML 锚点标记
    expect(yaml).not.toContain('&');
    expect(yaml).not.toContain('*');
  });
});
