import { describe, it, expect } from 'vitest';
import type { PipelineDetail } from '@/types';
import { yamlToNodes } from '../yamlToNodes';

/**
 * TDD: YAML → Nodes/Edges 反序列化
 * 将 PipelineDetail 转换为 React Flow 可编辑节点和边
 */

function makeMinimalPipeline(): PipelineDetail {
  return { name: 'test', pipelines: [] };
}

describe('YAML to Nodes deserialization', () => {
  describe('basic pipeline structure', () => {
    it('空 pipeline 生成 start/end 节点', () => {
      const { nodes, edges } = yamlToNodes(makeMinimalPipeline());
      const startNode = nodes.find(n => n.id === '__start__');
      const endNode = nodes.find(n => n.id === '__end__');
      expect(startNode).toBeDefined();
      expect(endNode).toBeDefined();
      expect(startNode?.type).toBe('editorStartEnd');
      expect(startNode?.data?.variant).toBe('start');
    });

    it('pipeline name 存入 pipeline 节点 data', () => {
      const { nodes } = yamlToNodes({ name: 'my-pipeline', pipelines: [], tasks: [] });
      const pNode = nodes.find(n => n.id === '__pipeline__');
      expect(pNode).toBeDefined();
      expect(pNode?.data?.label).toBe('my-pipeline');
    });

    it('生成 start → pipeline → end 的默认边', () => {
      const { edges } = yamlToNodes(makeMinimalPipeline());
      const startEdge = edges.find(e => e.source === '__start__' && e.target === '__pipeline__');
      const endEdge = edges.find(e => e.source === '__pipeline__' && e.target === '__end__');
      expect(startEdge).toBeDefined();
      expect(endEdge).toBeDefined();
    });
  });

  describe('subpipeline nodes', () => {
    it('每个 SubPipeline 生成一个容器节点', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [
          { name: 'build', depends_on: [], tasks: [] },
          { name: 'deploy', depends_on: [], tasks: [] },
        ],
      });

      const buildNode = nodes.find(n => n.data?.label === 'build' && n.type === 'editorSubPipeline');
      const deployNode = nodes.find(n => n.data?.label === 'deploy' && n.type === 'editorSubPipeline');
      expect(buildNode).toBeDefined();
      expect(deployNode).toBeDefined();
    });

    it('SubPipeline depends_on 生成跨容器边', () => {
      const { edges } = yamlToNodes({
        name: 'main',
        pipelines: [
          { name: 'build', depends_on: [], tasks: [{ name: 'a', env: {}, retry: 0, depends_on: [] }] },
          { name: 'deploy', depends_on: ['build'], tasks: [{ name: 'b', env: {}, retry: 0, depends_on: [] }] },
        ],
      });

      const crossEdge = edges.find(e =>
        e.source === '__pipeline__build' && e.target === '__pipeline__deploy'
      );
      expect(crossEdge).toBeDefined();
    });
  });

  describe('task nodes', () => {
    it('SubPipeline 内 tasks 生成 task 节点', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [
            { name: 'compile', env: {}, retry: 0, depends_on: [] },
            { name: 'test', env: {}, retry: 0, depends_on: [] },
          ],
        }],
      });

      const compileNode = nodes.find(n => n.data?.task?.name === 'compile');
      const testNode = nodes.find(n => n.data?.task?.name === 'test');
      expect(compileNode).toBeDefined();
      expect(testNode).toBeDefined();
      expect(compileNode?.type).toBe('editorTask');
      expect(compileNode?.parentId).toContain('build');
    });

    it('task depends_on 生成显式边', () => {
      const { edges } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [
            { name: 'compile', env: {}, retry: 0, depends_on: [] },
            { name: 'test', env: {}, retry: 0, depends_on: ['compile'] },
          ],
        }],
      });

      const depEdge = edges.find(e =>
        e.data?.edgeType === 'explicit' &&
        e.data?.sourceTask === 'compile' &&
        e.data?.targetTask === 'test'
      );
      expect(depEdge).toBeDefined();
    });

    it('sequential 策略生成隐式边', () => {
      const { edges } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build',
          config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'sequential' },
          depends_on: [],
          tasks: [
            { name: 'a', env: {}, retry: 0, depends_on: [] },
            { name: 'b', env: {}, retry: 0, depends_on: [] },
          ],
        }],
      });

      const implicitEdge = edges.find(e =>
        e.data?.edgeType === 'implicit'
      );
      expect(implicitEdge).toBeDefined();
    });

    it('task 类型推断: command', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build', depends_on: [], tasks: [
            { name: 'cmd1', command: 'echo hi', env: {}, retry: 0, depends_on: [] },
          ],
        }],
      });
      const cmdNode = nodes.find(n => n.data?.task?.name === 'cmd1');
      expect(cmdNode?.data?.taskType).toBe('command');
    });

    it('task 类型推断: invoke / steps / plugin', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build', depends_on: [], tasks: [
            { name: 'inv', invoke: { task: 'x', args: [], kwargs: {} }, env: {}, retry: 0, depends_on: [] },
            { name: 'stp', steps: [{ run: 'echo', env: {} }], env: {}, retry: 0, depends_on: [] },
            { name: 'plg', plugin: 'docker', env: {}, retry: 0, depends_on: [] },
          ],
        }],
      });

      const invNode = nodes.find(n => n.data?.task?.name === 'inv');
      const stpNode = nodes.find(n => n.data?.task?.name === 'stp');
      const plgNode = nodes.find(n => n.data?.task?.name === 'plg');
      expect(invNode?.data?.taskType).toBe('invoke');
      expect(stpNode?.data?.taskType).toBe('steps');
      expect(plgNode?.data?.taskType).toBe('plugin');
    });

    it('task with when 属性保留在 data 中', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build', depends_on: [], tasks: [
            { name: 'conditional', when: '${env.BRANCH} == main', env: {}, retry: 0, depends_on: [] },
          ],
        }],
      });
      const taskNode = nodes.find(n => n.data?.task?.name === 'conditional');
      expect(taskNode?.data?.task?.when).toBe('${env.BRANCH} == main');
    });
  });

  describe('post handling', () => {
    it('SubPipeline post 配置生成 post 父容器和子容器', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }],
          post: {
            on_fail: [{ name: 'notify-fail', env: {}, retry: 0, depends_on: [] }],
            on_success: [{ name: 'notify-ok', env: {}, retry: 0, depends_on: [] }],
          },
        }],
      });

      const postParent = nodes.find(n => n.type === 'editorPostParent');
      expect(postParent).toBeDefined();

      const onFailChild = nodes.find(n => n.data?.postVariant === 'on_fail');
      const onSuccessChild = nodes.find(n => n.data?.postVariant === 'on_success');
      expect(onFailChild).toBeDefined();
      expect(onSuccessChild).toBeDefined();
    });
  });

  describe('execution_strategy', () => {
    it('SubPipeline config.execution_strategy 存入 data', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'parallel-build',
          config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel', max_concurrent_tasks: 3 },
          depends_on: [],
          tasks: [{ name: 'a', env: {}, retry: 0, depends_on: [] }],
        }],
      });

      const subNode = nodes.find(n => n.data?.label === 'parallel-build');
      expect(subNode?.data?.executionStrategy).toBe('parallel');
      expect(subNode?.data?.maxConcurrentTasks).toBe(3);
    });

    it('继承顶层 execution_strategy', () => {
      const { nodes } = yamlToNodes({
        name: 'main',
        options: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel' },
        pipelines: [{
          name: 'deploy',
          depends_on: [],
          tasks: [{ name: 'a', env: {}, retry: 0, depends_on: [] }],
        }],
      });

      const subNode = nodes.find(n => n.data?.label === 'deploy');
      expect(subNode?.data?.executionStrategy).toBe('parallel');
    });
  });

  describe('edge metadata', () => {
    it('显式边包含 subpipelineName 和 taskName 信息', () => {
      const { edges } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [
            { name: 'a', env: {}, retry: 0, depends_on: [] },
            { name: 'b', env: {}, retry: 0, depends_on: ['a'] },
          ],
        }],
      });

      const depEdge = edges.find(e => e.data?.edgeType === 'explicit');
      expect(depEdge).toBeDefined();
      expect(depEdge?.data?.explicit).toBe(true);
      expect(depEdge?.data?.implicit).toBe(false);
    });

    it('隐式边标记 implicit=true, explicit=false', () => {
      const { edges } = yamlToNodes({
        name: 'main',
        pipelines: [{
          name: 'build',
          config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'sequential' },
          depends_on: [],
          tasks: [
            { name: 'a', env: {}, retry: 0, depends_on: [] },
            { name: 'b', env: {}, retry: 0, depends_on: [] },
          ],
        }],
      });

      const implicitEdge = edges.find(e => e.data?.edgeType === 'implicit');
      expect(implicitEdge).toBeDefined();
      expect(implicitEdge?.data?.implicit).toBe(true);
      expect(implicitEdge?.data?.explicit).toBe(false);
    });
  });
});

describe('YAML to Nodes container hierarchy', () => {
  it('task 节点的 parentId 指向其 SubPipeline 的容器节点', () => {
    const { nodes } = yamlToNodes({
      name: 'main',
      pipelines: [{
        name: 'build',
        depends_on: [],
        tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }],
      }],
    });

    const taskNode = nodes.find(n => n.data?.task?.name === 'compile');
    const subNode = nodes.find(n => n.data?.label === 'build' && n.type === 'editorSubPipeline');
    expect(taskNode?.parentId).toBe(subNode?.id);
  });

  it('post 子容器的 parentId 指向 post 父容器', () => {
    const { nodes } = yamlToNodes({
      name: 'main',
      pipelines: [{
        name: 'build',
        depends_on: [],
        tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }],
        post: {
          on_fail: [{ name: 'notify', env: {}, retry: 0, depends_on: [] }],
        },
      }],
    });

    const postParent = nodes.find(n => n.type === 'editorPostParent');
    const postChild = nodes.find(n => n.data?.postVariant === 'on_fail');
    expect(postParent).toBeDefined();
    expect(postChild).toBeDefined();
    expect(postChild?.parentId).toBe(postParent?.id);
  });
});

describe('YAML to Nodes maintains node IDs', () => {
  it('task 节点 ID 格式为 __task__<subName>.<taskName>', () => {
    const { nodes } = yamlToNodes({
      name: 'main',
      pipelines: [{
        name: 'build',
        depends_on: [],
        tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }],
      }],
    });

    const taskNode = nodes.find(n => n.data?.task?.name === 'compile');
    expect(taskNode?.id).toBe('__task__build.compile');
  });

  it('SubPipeline 节点 ID 格式为 __pipeline__<name>', () => {
    const { nodes } = yamlToNodes({
      name: 'main',
      pipelines: [
        { name: 'build', depends_on: [], tasks: [] },
      ],
    });

    const subNode = nodes.find(n => n.data?.label === 'build');
    expect(subNode?.id).toBe('__pipeline__build');
  });

  it('同一个 pipeline 多次调用生成相同的 ID', () => {
    const p: PipelineDetail = {
      name: 'main',
      pipelines: [{ name: 'build', depends_on: [], tasks: [{ name: 'a', env: {}, retry: 0, depends_on: [] }] }],
    };

    const r1 = yamlToNodes(p);
    const r2 = yamlToNodes(p);

    const ids1 = r1.nodes.map(n => n.id).sort();
    const ids2 = r2.nodes.map(n => n.id).sort();
    expect(ids1).toEqual(ids2);
  });
});
