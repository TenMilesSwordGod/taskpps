import { describe, it, expect } from 'vitest';
import { parseYamlToPipeline, pipelineToYaml } from '../yamlParser';
import type { PipelineDetail } from '@/types';

describe('yamlParser 并发/竞态测试', () => {
  it('快速连续解析多次（模拟 debounce 场景）', () => {
    const results = [];
    for (let i = 0; i < 100; i++) {
      const yaml = `name: pipeline-${i}\npipelines:\n  - name: stage\n    tasks:\n      - name: t\n        command: echo ${i}`;
      results.push(parseYamlToPipeline(yaml));
    }
    expect(results).toHaveLength(100);
    results.forEach((r, i) => {
      expect(r.success).toBe(true);
      expect(r.pipeline?.name).toBe(`pipeline-${i}`);
    });
  });

  it('交错解析有效和无效 YAML', () => {
    const inputs = [
      { text: 'name: valid\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo', expectValid: true },
      { text: 'name: [invalid', expectValid: false },
      { text: '', expectValid: false },
      { text: 'name: another-valid', expectValid: true },
      { text: '42', expectValid: false },
    ];

    inputs.forEach(({ text, expectValid }) => {
      const result = parseYamlToPipeline(text);
      expect(result.success).toBe(expectValid);
    });
  });

  it('pipelineToYaml 和 parseYamlToPipeline 交替调用不互相影响', () => {
    const pipeline: PipelineDetail = {
      name: 'roundtrip',
      pipelines: [{ name: 's', depends_on: [], tasks: [{ name: 't', command: 'echo', env: {}, retry: 0, depends_on: [] }] }],
    };

    for (let i = 0; i < 50; i++) {
      const yaml = pipelineToYaml(pipeline);
      const result = parseYamlToPipeline(yaml);
      expect(result.success).toBe(true);
      expect(result.pipeline?.name).toBe('roundtrip');
    }
  });

  it('解析失败后立即解析有效内容恢复正常', () => {
    const failResult = parseYamlToPipeline('name: [broken');
    expect(failResult.success).toBe(false);

    const okResult = parseYamlToPipeline('name: recovered\npipelines:\n  - name: a\n    tasks:\n      - name: t\n        command: echo');
    expect(okResult.success).toBe(true);
    expect(okResult.pipeline?.name).toBe('recovered');
  });

  it('模拟快速编辑：每次只改一个字符', () => {
    const base = 'name: test\npipelines:\n  - name: stage\n    tasks:\n      - name: t\n        command: echo';
    for (let i = 0; i < base.length; i++) {
      const modified = base.slice(0, i) + 'X' + base.slice(i + 1);
      const result = parseYamlToPipeline(modified);
      // 不关心是否成功，只关心不崩溃
      expect(result).toHaveProperty('success');
    }
  });
});
