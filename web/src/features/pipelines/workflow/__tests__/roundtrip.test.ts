import { describe, it, expect } from 'vitest';
import type { PipelineDetail } from '@/types';
import { yamlToNodes } from '../yamlToNodes';
import { nodesToYaml } from '../nodesToYaml';

/**
 * YAML 往返一致性测试
 * 验证 序列化 → 反序列化 → 序列化 的完整性
 *
 * 核心检查点:
 *   1. Pipeline name 保持不变
 *   2. SubPipeline 名称和数量一致
 *   3. Task 名称、数量和 depends_on 关系一致
 *   4. Post 钩子结构完整
 *   5. execution_strategy 属性保留
 *   6. when 条件保留
 *   7. 两次序列化生成一致的 YAML 结构
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const vi: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const describe: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const it: any;

describe('YAML 往返一致性 (Round-trip)', () => {
  describe('多层嵌套 Pipeline', () => {
    it('双层 SubPipeline → Task → 原子节点往返', () => {
      const original: PipelineDetail = {
        name: 'nested-pipeline',
        pipelines: [
          {
            name: 'build',
            depends_on: [],
            tasks: [
              {
                name: 'compile',
                command: 'gcc -o main main.c',
                env: { CC: '/usr/bin/gcc' },
                retry: 1,
                depends_on: [],
              },
              {
                name: 'link',
                command: 'ld main.o',
                env: {},
                retry: 0,
                depends_on: ['compile'],
              },
            ],
          },
          {
            name: 'test',
            depends_on: ['build'],
            config: {
              env: {},
              retry: 0,
              on_failure: 'stop',
              execution_strategy: 'parallel',
              max_concurrent_tasks: 2,
            },
            tasks: [
              {
                name: 'unit-test',
                command: 'pytest tests/unit',
                env: { PYTHONPATH: '.' },
                retry: 0,
                depends_on: [],
              },
              {
                name: 'integration-test',
                command: 'pytest tests/integration',
                env: {},
                retry: 1,
                depends_on: [],
              },
            ],
          },
        ],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      expect(restored).not.toBeNull();
      expect(restored?.name).toBe('nested-pipeline');

      const buildSub = restored?.pipelines?.find(s => s.name === 'build');
      expect(buildSub).toBeDefined();
      expect(buildSub?.tasks.length).toBe(2);

      // 验证 compile task 属性
      const compileTask = buildSub?.tasks.find(t => t.name === 'compile');
      expect(compileTask?.command).toBe('gcc -o main main.c');
      expect(compileTask?.retry).toBe(1);
      expect(compileTask?.env?.CC).toBe('/usr/bin/gcc');

      // 验证 depends_on 关系保留
      const linkTask = buildSub?.tasks.find(t => t.name === 'link');
      expect(linkTask?.depends_on).toContain('compile');

      // 验证 test SubPipeline 的并行策略
      const testSub = restored?.pipelines?.find(s => s.name === 'test');
      expect(testSub?.config?.execution_strategy).toBe('parallel');
      expect(testSub?.config?.max_concurrent_tasks).toBe(2);
      expect(testSub?.tasks.length).toBe(2);

      // 验证 depends_on（跨 SubPipeline）
      expect(testSub?.depends_on).toContain('build');
    });
  });

  describe('WHEN 条件往返', () => {
    it('task with when 条件完整保留', () => {
      const original: PipelineDetail = {
        name: 'when-test',
        pipelines: [{
          name: 'deploy',
          depends_on: [],
          tasks: [
            {
              name: 'deploy-prod',
              command: 'kubectl apply',
              when: '${env.BRANCH} == main',
              env: {},
              retry: 0,
              depends_on: [],
            },
            {
              name: 'deploy-dev',
              command: 'kubectl apply',
              when: '${env.BRANCH} != main',
              env: {},
              retry: 0,
              depends_on: [],
            },
          ],
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const deploySub = restored?.pipelines?.find(s => s.name === 'deploy');
      const prodTask = deploySub?.tasks.find(t => t.name === 'deploy-prod');
      const devTask = deploySub?.tasks.find(t => t.name === 'deploy-dev');
      expect(prodTask?.when).toBe('${env.BRANCH} == main');
      expect(devTask?.when).toBe('${env.BRANCH} != main');
    });
  });

  describe('execution_strategy 继承', () => {
    it('顶层 options.execution_strategy 被子 SubPipeline 继承并保留', () => {
      const original: PipelineDetail = {
        name: 'inherit-test',
        options: {
          env: {},
          retry: 0,
          on_failure: 'stop',
          execution_strategy: 'parallel',
          max_concurrent_tasks: 5,
        },
        pipelines: [
          { name: 'a', depends_on: [], tasks: [
            { name: 't1', env: {}, retry: 0, depends_on: [] },
          ]},
          // b 显式覆盖 strategy
          {
            name: 'b',
            config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'sequential' },
            depends_on: [],
            tasks: [{ name: 't2', env: {}, retry: 0, depends_on: [] }],
          },
        ],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      // a 继承了顶层的 parallel + maxConcurrentTasks
      const subA = restored?.pipelines?.find(s => s.name === 'a');
      expect(subA?.config?.execution_strategy).toBe('parallel');
      expect(subA?.config?.max_concurrent_tasks).toBe(5);

      // b 覆盖了 sequential，max_concurrent_tasks 也保留
      const subB = restored?.pipelines?.find(s => s.name === 'b');
      expect(subB?.config?.execution_strategy).toBe('sequential');
    });
  });

  describe('Post 钩子完整往返', () => {
    it('on_fail / on_success / always 三类 Post 往返', () => {
      const original: PipelineDetail = {
        name: 'full-post',
        pipelines: [{
          name: 'deploy',
          depends_on: [],
          tasks: [{ name: 'deploy', command: 'deploy.sh', env: {}, retry: 0, depends_on: [] }],
          post: {
            on_fail: [{ name: 'notify-fail', command: 'echo FAIL', env: {}, retry: 0, depends_on: [] }],
            on_success: [{ name: 'notify-ok', command: 'echo OK', env: {}, retry: 0, depends_on: [] }],
            always: [{ name: 'cleanup', command: 'rm -rf /tmp', env: {}, retry: 0, depends_on: [] }],
          },
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const deploySub = restored?.pipelines?.find(s => s.name === 'deploy');
      expect(deploySub?.post?.on_fail).toBeDefined();
      expect(deploySub?.post?.on_success).toBeDefined();
      expect(deploySub?.post?.always).toBeDefined();

      expect(deploySub?.post?.on_fail?.[0].name).toBe('notify-fail');
      expect(deploySub?.post?.on_fail?.[0].command).toBe('echo FAIL');
      expect(deploySub?.post?.on_success?.[0].name).toBe('notify-ok');
      expect(deploySub?.post?.always?.[0].name).toBe('cleanup');
    });

    it('多个相同 Post 类型的 task', () => {
      const original: PipelineDetail = {
        name: 'multi-post',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }],
          post: {
            on_fail: [
              { name: 'slack', command: 'curl slack', env: {}, retry: 0, depends_on: [] },
              { name: 'email', command: 'sendmail', env: {}, retry: 0, depends_on: [] },
            ],
          },
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const buildSub = restored?.pipelines?.find(s => s.name === 'build');
      expect(buildSub?.post?.on_fail?.length).toBe(2);
      expect(buildSub?.post?.on_fail?.map((t: { name: string }) => t.name).sort())
        .toEqual(['email', 'slack']);
    });
  });

  describe('任务类型往返 (type inference)', () => {
    it('所有原子任务类型完整保留', () => {
      const original: PipelineDetail = {
        name: 'type-test',
        pipelines: [{
          name: 'all',
          depends_on: [],
          tasks: [
            { name: 'cmd1', command: 'echo hi', env: {}, retry: 0, depends_on: [] },
            { name: 'stp1', steps: [{ run: 'ls', env: {} }], env: {}, retry: 0, depends_on: [] },
            { name: 'plg1', plugin: 'docker', env: {}, retry: 0, depends_on: [] },
            { name: 'inv1', invoke: { task: 'build', args: [], kwargs: {} }, env: {}, retry: 0, depends_on: [] },
          ],
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const sub = restored?.pipelines?.find(s => s.name === 'all');
      expect(sub?.tasks.find(t => t.name === 'cmd1')?.command).toBe('echo hi');
      expect(sub?.tasks.find(t => t.name === 'stp1')?.steps?.[0].run).toBe('ls');
      expect(sub?.tasks.find(t => t.name === 'plg1')?.plugin).toBe('docker');
      expect(sub?.tasks.find(t => t.name === 'inv1')?.invoke?.task).toBe('build');
    });
  });

  describe('两次序列化一致性', () => {
    it('两次 serialization 生成完全一致的 PipelineDetail', () => {
      const original: PipelineDetail = {
        name: 'idempotent',
        pipelines: [
          {
            name: 'build',
            depends_on: [],
            config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'sequential' },
            tasks: [
              { name: 'compile', command: 'make', env: { DEBUG: '1' }, retry: 0, depends_on: [] },
              { name: 'test', command: 'pytest', env: {}, retry: 1, depends_on: ['compile'] },
            ],
            post: {
              on_success: [{ name: 'tag', command: 'git tag', env: {}, retry: 0, depends_on: [] }],
            },
          },
        ],
      };

      // 第一次序列化
      const { nodes: nodes1, edges: edges1 } = yamlToNodes(original);
      const { pipeline: p1 } = nodesToYaml(nodes1, edges1);
      expect(p1).not.toBeNull();

      // 第二次序列化（从恢复的数据再次反序列化+序列化）
      const { nodes: nodes2, edges: edges2 } = yamlToNodes(p1!);
      const { pipeline: p2, errors: e2 } = nodesToYaml(nodes2, edges2);

      expect(e2).toEqual([]);
      expect(p2).not.toBeNull();

      // 验证两次序列化结果在核心字段上一致
      expect(p1?.name).toBe(p2?.name);
      expect(p1?.pipelines?.length).toBe(p2?.pipelines?.length);

      const sub1 = p1?.pipelines?.[0];
      const sub2 = p2?.pipelines?.[0];
      expect(sub1?.name).toBe(sub2?.name);
      expect(sub1?.tasks.length).toBe(sub2?.tasks.length);
      expect(sub1?.config?.execution_strategy).toBe(sub2?.config?.execution_strategy);

      const compile1 = sub1?.tasks.find(t => t.name === 'compile');
      const compile2 = sub2?.tasks.find(t => t.name === 'compile');
      expect(compile1?.env?.DEBUG).toBe(compile2?.env?.DEBUG);
      expect(compile1?.command).toBe(compile2?.command);

      // Post 一致性
      expect(sub1?.post?.on_success?.length).toBe(sub2?.post?.on_success?.length);
    });
  });
});

describe('YAML ↔ Nodes 数据完整性', () => {
  it('SubPipeline depends_on 跨容器边往返', () => {
    const original: PipelineDetail = {
      name: 'cross-ref',
      pipelines: [
        { name: 'phase1', depends_on: [], tasks: [{ name: 't1', env: {}, retry: 0, depends_on: [] }] },
        { name: 'phase2', depends_on: ['phase1'], tasks: [{ name: 't2', env: {}, retry: 0, depends_on: [] }] },
        { name: 'phase3', depends_on: ['phase1', 'phase2'], tasks: [{ name: 't3', env: {}, retry: 0, depends_on: [] }] },
      ],
    };

    const { nodes, edges } = yamlToNodes(original);
    const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

    expect(errors).toEqual([]);
    expect(restored?.pipelines?.length).toBe(3);

    const p2 = restored?.pipelines?.find(s => s.name === 'phase2');
    const p3 = restored?.pipelines?.find(s => s.name === 'phase3');
    expect(p2?.depends_on).toContain('phase1');
    expect(p3?.depends_on).toContain('phase1');
    expect(p3?.depends_on).toContain('phase2');
  });
});
