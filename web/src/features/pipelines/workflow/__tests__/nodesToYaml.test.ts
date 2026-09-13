import { describe, it, expect } from 'vitest';
import type { Node, Edge } from '@xyflow/react';
import { nodesToYaml } from '../nodesToYaml';
import { yamlToNodes } from '../yamlToNodes';
import type { PipelineDetail } from '@/types';
import type { EditorNodeData, EditorEdgeData } from '../yamlToNodes';

/**
 * TDD: Nodes/Edges → YAML 序列化
 * 将画布状态转换回 PipelineDetail 以确保 YAML 写回正确
 */

describe('Nodes to YAML serialization', () => {
  describe('round-trip', () => {
    it('简单 pipeline YAML → nodes → YAML 无损', () => {
      const original: PipelineDetail = {
        name: 'test-roundtrip',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [
            { name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] },
            { name: 'test', command: 'pytest', env: {}, retry: 1, depends_on: ['compile'] },
          ],
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      expect(restored).not.toBeNull();
      expect(restored?.name).toBe('test-roundtrip');

      const buildSub = restored?.pipelines?.find(s => s.name === 'build');
      expect(buildSub).toBeDefined();
      expect(buildSub?.tasks.length).toBe(2);

      const compileTask = buildSub?.tasks.find(t => t.name === 'compile');
      expect(compileTask).toBeDefined();
      expect(compileTask?.depends_on).toEqual([]);

      const testTask = buildSub?.tasks.find(t => t.name === 'test');
      expect(testTask).toBeDefined();
      expect(testTask?.depends_on).toContain('compile');
    });

    it('多 SubPipeline 往返保持 depends_on', () => {
      const original: PipelineDetail = {
        name: 'multi',
        pipelines: [
          { name: 'build', depends_on: [], tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }] },
          { name: 'deploy', depends_on: ['build'], tasks: [{ name: 'scp', env: {}, retry: 0, depends_on: [] }] },
        ],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const deploySub = restored?.pipelines?.find(s => s.name === 'deploy');
      expect(deploySub?.depends_on).toContain('build');
    });
  });

  describe('execution_strategy', () => {
    it('parallel 策略保留', () => {
      const original: PipelineDetail = {
        name: 'parallel-test',
        pipelines: [{
          name: 'build',
          config: {
            env: {},
            retry: 0,
            on_failure: 'stop',
            execution_strategy: 'parallel',
            max_concurrent_tasks: 3,
          },
          depends_on: [],
          tasks: [{ name: 'a', env: {}, retry: 0, depends_on: [] }],
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const buildSub = restored?.pipelines?.find(s => s.name === 'build');
      expect(buildSub?.config?.execution_strategy).toBe('parallel');
      expect(buildSub?.config?.max_concurrent_tasks).toBe(3);
    });
  });

  describe('post handling', () => {
    it('Post 钩子数据正确序列化', () => {
      const original: PipelineDetail = {
        name: 'post-test',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [{ name: 'compile', env: {}, retry: 0, depends_on: [] }],
          post: {
            on_fail: [{ name: 'notify-fail', command: 'echo fail', env: {}, retry: 0, depends_on: [] }],
            on_success: [{ name: 'notify-ok', command: 'echo ok', env: {}, retry: 0, depends_on: [] }],
          },
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const buildSub = restored?.pipelines?.find(s => s.name === 'build');
      expect(buildSub?.post?.on_fail).toBeDefined();
      expect(buildSub?.post?.on_success).toBeDefined();
      expect(buildSub?.post?.on_fail?.length).toBeGreaterThan(0);
      expect(buildSub?.post?.on_fail?.[0].name).toBe('notify-fail');
    });
  });

  describe('task type inference', () => {
    it('CMD / STEP / PLUGIN / INVOKE 类型保留', () => {
      const original: PipelineDetail = {
        name: 'type-test',
        pipelines: [{
          name: 'build',
          depends_on: [],
          tasks: [
            { name: 'cmd', command: 'echo', env: {}, retry: 0, depends_on: [] },
            { name: 'steps', steps: [{ run: 'echo', env: {} }], env: {}, retry: 0, depends_on: [] },
            { name: 'plugin', plugin: 'docker', env: {}, retry: 0, depends_on: [] },
            { name: 'invoke', invoke: { task: 'x', args: [], kwargs: {} }, env: {}, retry: 0, depends_on: [] },
          ],
        }],
      };

      const { nodes, edges } = yamlToNodes(original);
      const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

      expect(errors).toEqual([]);
      const buildSub = restored?.pipelines?.find(s => s.name === 'build');

      const cmdTask = buildSub?.tasks.find(t => t.name === 'cmd');
      expect(cmdTask?.command).toBe('echo');

      const stepsTask = buildSub?.tasks.find(t => t.name === 'steps');
      expect(stepsTask?.steps?.[0].run).toBe('echo');

      const pluginTask = buildSub?.tasks.find(t => t.name === 'plugin');
      expect(pluginTask?.plugin).toBe('docker');

      const invokeTask = buildSub?.tasks.find(t => t.name === 'invoke');
      expect(invokeTask?.invoke?.task).toBe('x');
    });
  });

  describe('validation errors', () => {
    it('空 nodes → 生成空 pipeline', () => {
      const { pipeline, errors } = nodesToYaml([], []);
      expect(pipeline).toBeDefined();
      expect(pipelinesIsEmpty(pipeline));
    });

    it('无 SubPipeline 归属的 task → 包装为同名隐式 SubPipeline（对齐后端 _normalize）', () => {
      const nodes: Node<EditorNodeData>[] = [
        {
          id: 'orphan-task',
          type: 'editorTask',
          position: { x: 0, y: 0 },
          data: { task: { name: 'orphan', env: {}, retry: 0, depends_on: [] }, taskType: 'command' },
        },
        {
          id: '__pipeline__',
          type: 'editorPipeline',
          position: { x: 0, y: 0 },
          data: { label: 'test' },
        },
      ];

      // v3 (2026-07): 根级 task 不再报错/丢失，而是包装成以流水线名命名的隐式 SubPipeline，
      // 保证后端（pipelines 优先解析）也会执行这些任务，不静默丢数据。
      const { pipeline, errors } = nodesToYaml(nodes, []);
      expect(errors).toEqual([]);
      const implicit = pipeline?.pipelines?.find(s => s.name === 'test');
      expect(implicit?.tasks.map(t => t.name)).toEqual(['orphan']);
    });
  });

  describe('edge dependency extraction', () => {
    it('显式边 → depends_on，隐式边不写入', () => {
      // 构造包含显式和隐式边的场景
      const nodes: Node<EditorNodeData>[] = [
        { id: '__start__', type: 'editorStartEnd', position: { x: 0, y: 0 }, data: { variant: 'start' } },
        { id: '__end__', type: 'editorStartEnd', position: { x: 800, y: 600 }, data: { variant: 'end' } },
        {
          id: '__pipeline__',
          type: 'editorPipeline',
          position: { x: 0, y: 0 },
          style: { width: 800, height: 400 },
          data: { label: 'test' },
        },
        {
          id: '__pipeline__build',
          type: 'editorSubPipeline',
          parentId: '__pipeline__',
          position: { x: 40, y: 40 },
          style: { width: 260, height: 200 },
          data: { label: 'build', executionStrategy: 'sequential' },
        },
        {
          id: '__task__build.a',
          type: 'editorTask',
          parentId: '__pipeline__build',
          position: { x: 60, y: 80 },
          data: { task: { name: 'a', env: {}, retry: 0, depends_on: [] }, taskType: 'command', subpipelineName: 'build' },
        },
        {
          id: '__task__build.b',
          type: 'editorTask',
          parentId: '__pipeline__build',
          position: { x: 60, y: 216 },
          data: { task: { name: 'b', env: {}, retry: 0, depends_on: [] }, taskType: 'command', subpipelineName: 'build' },
        },
      ];

      const edges: Edge<EditorEdgeData>[] = [
        {
          id: '__edge__explicit_a_to_b',
          source: '__task__build.a',
          target: '__task__build.b',
          type: 'smoothstep',
          data: { edgeType: 'explicit', subpipelineName: 'build', sourceTask: 'a', targetTask: 'b', explicit: true, implicit: false },
        },
        {
          id: '__edge__start_pipeline',
          source: '__start__',
          target: '__pipeline__',
          type: 'smoothstep',
          data: { edgeType: 'cross_container', explicit: true, implicit: false },
        },
      ];

      const { pipeline, errors } = nodesToYaml(nodes, edges);
      expect(errors).toEqual([]);

      const buildSub = pipeline?.pipelines?.find(s => s.name === 'build');
      const taskB = buildSub?.tasks.find(t => t.name === 'b');
      expect(taskB?.depends_on).toContain('a');
    });
  });

  describe('v3 结构解析与跨容器连线', () => {
    const pipelineNode: Node<EditorNodeData> = {
      id: '__pipeline__',
      type: 'editorPipeline',
      position: { x: 0, y: 0 },
      data: { label: 'test-v3' },
    };
    const makeSubNode = (id: string, label: string): Node<EditorNodeData> => ({
      id,
      type: 'editorSubPipeline',
      parentId: '__pipeline__',
      position: { x: 0, y: 0 },
      data: { label, executionStrategy: 'sequential' },
    });
    const makeTaskNode = (
      id: string,
      parentId: string | undefined,
      name: string,
      subpipelineName?: string,
    ): Node<EditorNodeData> => ({
      id,
      type: 'editorTask',
      parentId,
      position: { x: 0, y: 0 },
      data: {
        task: { name, env: {}, retry: 0, depends_on: [] },
        taskType: 'command',
        ...(subpipelineName !== undefined ? { subpipelineName } : {}),
      },
    });

    it('拖拽新增的 task（subpipelineName 为空）按 parentId 归入 SubPipeline', () => {
      const nodes = [
        pipelineNode,
        makeSubNode('__pipeline__build', 'build'),
        makeTaskNode('__new__1', '__pipeline__build', 'dragged'), // 模拟拖拽新增：无 subpipelineName
      ];
      const { pipeline, errors } = nodesToYaml(nodes, []);
      expect(errors).toEqual([]);
      const build = pipeline?.pipelines?.find(s => s.name === 'build');
      expect(build?.tasks.map(t => t.name)).toEqual(['dragged']);
    });

    it('跨容器 task→task 手动连线映射为 target sub 的 depends_on', () => {
      const nodes = [
        pipelineNode,
        makeSubNode('__pipeline__build', 'build'),
        makeSubNode('__pipeline__deploy', 'deploy'),
        makeTaskNode('__task__build.compile', '__pipeline__build', 'compile', 'build'),
        makeTaskNode('__task__deploy.push', '__pipeline__deploy', 'push', 'deploy'),
      ];
      const edges: Edge<EditorEdgeData>[] = [
        {
          id: 'manual-cross',
          source: '__task__build.compile',
          target: '__task__deploy.push',
          type: 'smoothstep',
          data: { edgeType: 'explicit', explicit: true, implicit: false },
        },
      ];
      const { pipeline, errors } = nodesToYaml(nodes, edges);
      expect(errors).toEqual([]);
      const deploy = pipeline?.pipelines?.find(s => s.name === 'deploy');
      expect(deploy?.depends_on).toContain('build');
    });

    it('sub→sub 手动连线映射为 depends_on', () => {
      const nodes = [
        pipelineNode,
        makeSubNode('__pipeline__a', 'a'),
        makeSubNode('__pipeline__b', 'b'),
        makeTaskNode('__task__a.t', '__pipeline__a', 't', 'a'),
        makeTaskNode('__task__b.t', '__pipeline__b', 't', 'b'),
      ];
      const edges: Edge<EditorEdgeData>[] = [
        {
          id: 'manual-sub',
          source: '__pipeline__a',
          target: '__pipeline__b',
          type: 'smoothstep',
          data: { edgeType: 'explicit', explicit: true, implicit: false },
        },
      ];
      const { pipeline, errors } = nodesToYaml(nodes, edges);
      expect(errors).toEqual([]);
      expect(pipeline?.pipelines?.find(s => s.name === 'b')?.depends_on).toContain('a');
    });

    it('START→END 直连 → 报错而非静默丢弃', () => {
      const nodes: Node<EditorNodeData>[] = [
        pipelineNode,
        { id: '__start__', type: 'editorStartEnd', position: { x: 0, y: 0 }, data: { variant: 'start' } },
        { id: '__end__', type: 'editorStartEnd', position: { x: 0, y: 200 }, data: { variant: 'end' } },
      ];
      const edges: Edge<EditorEdgeData>[] = [
        {
          id: 'start-to-end',
          source: '__start__',
          target: '__end__',
          type: 'smoothstep',
          data: { edgeType: 'explicit', explicit: true, implicit: false },
        },
      ];
      const { pipeline, errors } = nodesToYaml(nodes, edges);
      expect(pipeline).toBeNull();
      expect(errors.join(' ')).toContain('无法保存的连线');
    });

    it('根级 task 之间的依赖写入隐式 sub 的 depends_on', () => {
      const nodes = [
        pipelineNode,
        makeTaskNode('__new__a', undefined, 'a'),
        makeTaskNode('__new__b', undefined, 'b'),
      ];
      const edges: Edge<EditorEdgeData>[] = [
        {
          id: 'root-edge',
          source: '__new__a',
          target: '__new__b',
          type: 'smoothstep',
          data: { edgeType: 'explicit', explicit: true, implicit: false },
        },
      ];
      const { pipeline, errors } = nodesToYaml(nodes, edges);
      expect(errors).toEqual([]);
      const implicit = pipeline?.pipelines?.find(s => s.name === 'test-v3');
      expect(implicit?.tasks.map(t => t.name).sort()).toEqual(['a', 'b']);
      expect(implicit?.tasks.find(t => t.name === 'b')?.depends_on).toEqual(['a']);
    });
  });
});

/** 检查 pipeline 的 pipelines 数组是否为空 */
function pipelinesIsEmpty(p: PipelineDetail | null): boolean {
  return !p?.pipelines || p.pipelines.length === 0;
}
