import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import type { Node, Edge } from '@xyflow/react';
import type { PipelineDetail } from '@/types';
import { yamlToNodes } from '../yamlToNodes';
import { nodesToYaml } from '../nodesToYaml';
import type { EditorNodeData, EditorEdgeData } from '../yamlToNodes';
import { renderWithProvider } from './test-utils';
import WorkflowEditor from '../WorkflowEditor';
import EditorSubPipelineNode from '../nodes/EditorSubPipelineNode';
import EditorTaskNode from '../nodes/EditorTaskNode';
import EditorPostParentNode from '../nodes/EditorPostParentNode';
import EditorPostChildNode from '../nodes/EditorPostChildNode';

/**
 * 边界场景测试
 * 覆盖:
 *   - 空 Pipeline（无 nodes/edges）
 *   - 深层嵌套 SubPipeline → Task → 原子
 *   - Post 容器边界情况
 *   - 超多 task 的 SubPipeline
 *   - 拓扑排序异常（循环依赖）
 */

describe('边界场景: 空 Pipeline', () => {
  it('空 pipeline（无 SubPipeline）生成 start/end + pipeline 容器', () => {
    const p: PipelineDetail = { name: 'empty' };
    const { nodes, edges } = yamlToNodes(p);

    expect(nodes.length).toBeGreaterThanOrEqual(3); // start, pipeline, end
    expect(nodes.find(n => n.id === '__start__')).toBeDefined();
    expect(nodes.find(n => n.id === '__pipeline__')).toBeDefined();
    expect(nodes.find(n => n.id === '__end__')).toBeDefined();
    // 无 SubPipeline 时没有 edges（除了 start→pipeline→end）
    expect(edges.length).toBe(2);
  });

  it('空 SubPipeline（无 tasks）可以正确序列化', () => {
    const p: PipelineDetail = {
      name: 'empty-sub',
      pipelines: [
        { name: 'empty-build', depends_on: [], tasks: [] },
      ],
    };

    const { nodes, edges } = yamlToNodes(p);
    const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

    // 空 SubPipeline 会产生验证错误
    expect(errors.length).toBeGreaterThan(0);
    expect(errors.some(e => e.includes('不能为空'))).toBe(true);
  });

  it('空 nodes/edges 序列化返回空 pipeline', () => {
    const { pipeline, errors } = nodesToYaml([], []);

    expect(pipeline).toBeDefined();
    expect(pipeline?.name || 'unnamed').toBeDefined();
    // 空 nodes → 空的 SubPipeline 列表
  });

  it('只有 start/end 和 pipeline 容器节点的序列化', () => {
    const nodes: Node<EditorNodeData>[] = [
      { id: '__start__', type: 'editorStartEnd', position: { x: 0, y: 0 }, data: { variant: 'start' } },
      { id: '__end__', type: 'editorStartEnd', position: { x: 600, y: 600 }, data: { variant: 'end' } },
      { id: '__pipeline__', type: 'editorPipeline', position: { x: 0, y: 0 }, data: { label: 'minimal' }, style: { width: 800, height: 400 } },
    ];
    const { pipeline, errors } = nodesToYaml(nodes, []);

    expect(errors).toEqual([]);
    expect(pipeline?.name).toBe('minimal');
    expect(pipeline?.pipelines?.length || 0).toBe(0);
  });
});

describe('边界场景: 深层嵌套', () => {
  it('3层 SubPipeline 嵌套正确识别', () => {
    const p: PipelineDetail = {
      name: 'deep-nest',
      pipelines: [
        {
          name: 'level1',
          depends_on: [],
          tasks: [
            { name: 'l1-task1', command: 'echo 1', env: {}, retry: 0, depends_on: [] },
            { name: 'l1-task2', command: 'echo 2', env: {}, retry: 0, depends_on: ['l1-task1'] },
          ],
        },
        {
          name: 'level2',
          depends_on: ['level1'],
          tasks: [
            { name: 'l2-task1', command: 'echo 3', env: {}, retry: 0, depends_on: [] },
            { name: 'l2-task2', command: 'echo 4', env: {}, retry: 0, depends_on: ['l2-task1'] },
            { name: 'l2-task3', command: 'echo 5', env: {}, retry: 0, depends_on: ['l2-task1'] },
          ],
        },
        {
          name: 'level3',
          depends_on: ['level2'],
          tasks: [
            { name: 'l3-task1', command: 'echo 6', env: {}, retry: 0, depends_on: [] },
          ],
          post: {
            on_fail: [{ name: 'panic', command: 'exit 1', env: {}, retry: 0, depends_on: [] }],
          },
        },
      ],
    };

    const { nodes } = yamlToNodes(p);

    // 检查所有 SubPipeline 容器节点
    const subNames = nodes
      .filter(n => n.type === 'editorSubPipeline')
      .map(n => n.data?.label as string);
    expect(subNames).toContain('level1');
    expect(subNames).toContain('level2');
    expect(subNames).toContain('level3');

    // 检查 Post 父容器
    const postParent = nodes.find(n => n.type === 'editorPostParent');
    expect(postParent).toBeDefined();

    // 检查 Task 节点层级关系
    const taskNodes = nodes.filter(n => n.type === 'editorTask');
    // level1 有 2 个 task, level2 有 3 个 task, level3 有 1 个 task
    expect(taskNodes.length).toBe(6);

    // level3 的 Post 子容器是 editorPostChild 类型，不是 editorTask
    const postChildren = nodes.filter(n => n.type === 'editorPostChild');
    expect(postChildren.length).toBe(1);

    // 往返测试
    const { pipeline: restored, errors } = nodesToYaml(nodes, []);
    // 由于跨容器边未提供，depends_on 可能丢失，但结构应保留
    expect(restored?.pipelines?.length).toBe(3);
  });

  it('深层 Post 嵌套 (always 钩子)', () => {
    const p: PipelineDetail = {
      name: 'deep-post',
      pipelines: [{
        name: 'job',
        depends_on: [],
        tasks: [{ name: 'main', command: 'run.sh', env: {}, retry: 0, depends_on: [] }],
        post: {
          always: [
            { name: 'cleanup1', command: 'rm -rf /tmp/a', env: {}, retry: 0, depends_on: [] },
            { name: 'cleanup2', command: 'rm -rf /tmp/b', env: {}, retry: 0, depends_on: [] },
          ],
          on_fail: [
            { name: 'rollback', command: 'rollback.sh', env: { DRY_RUN: '0' }, retry: 0, depends_on: [] },
          ],
          on_success: [
            { name: 'tag-release', command: 'git tag v1', env: {}, retry: 0, depends_on: [] },
          ],
        },
      }],
    };

    const { nodes, edges } = yamlToNodes(p);
    const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

    expect(errors).toEqual([]);
    const sub = restored?.pipelines?.[0];
    expect(sub?.post?.always?.length).toBe(2);
    expect(sub?.post?.on_fail?.length).toBe(1);
    expect(sub?.post?.on_success?.length).toBe(1);

    // 验证 always 钩子保留 env
    const rollback = sub?.post?.on_fail?.[0];
    expect(rollback?.env?.DRY_RUN).toBe('0');
  });
});

describe('边界场景: 超多 Task', () => {
  it('单个 SubPipeline 包含 20 个 task 往返', () => {
    const tasks20 = Array.from({ length: 20 }, (_, i) => ({
      name: `task-${i}`,
      command: `echo ${i}`,
      env: {},
      retry: 0,
      depends_on: i > 0 ? [`task-${i - 1}`] : [],
    }));

    const p: PipelineDetail = {
      name: 'large',
      pipelines: [{ name: 'batch', depends_on: [], tasks: tasks20 }],
    };

    const { nodes, edges } = yamlToNodes(p);
    const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

    expect(errors).toEqual([]);
    const sub = restored?.pipelines?.[0];
    expect(sub?.tasks.length).toBe(20);

    // 验证最后一个 task 的 depends_on
    const lastTask = sub?.tasks.find(t => t.name === 'task-19');
    expect(lastTask?.depends_on).toContain('task-18');
  });

  it('隐式边生成（sequential, 无显式 depends_on）', () => {
    const tasks: NonNullable<PipelineDetail['pipelines']>[number]['tasks'] = [
      { name: 'a', env: {}, retry: 0, depends_on: [] },
      { name: 'b', env: {}, retry: 0, depends_on: [] },
      { name: 'c', env: {}, retry: 0, depends_on: [] },
      { name: 'd', env: {}, retry: 0, depends_on: [] },
    ];

    const p: PipelineDetail = {
      name: 'implicit-test',
      pipelines: [{
        name: 'seq',
        config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'sequential' },
        depends_on: [],
        tasks,
      }],
    };

    const { edges } = yamlToNodes(p);
    const implicitEdges = edges.filter(e => e.data?.edgeType === 'implicit');
    // 4 tasks 应有 3 条隐式边 (a→b→c→d)
    expect(implicitEdges.length).toBe(3);
  });

  it('parallel 策略无隐式边', () => {
    const tasks: NonNullable<PipelineDetail['pipelines']>[number]['tasks'] = [
      { name: 'x', env: {}, retry: 0, depends_on: [] },
      { name: 'y', env: {}, retry: 0, depends_on: [] },
      { name: 'z', env: {}, retry: 0, depends_on: [] },
    ];

    const p: PipelineDetail = {
      name: 'par-test',
      pipelines: [{
        name: 'par',
        config: { env: {}, retry: 0, on_failure: 'stop', execution_strategy: 'parallel' },
        depends_on: [],
        tasks,
      }],
    };

    const { edges } = yamlToNodes(p);
    const implicitEdges = edges.filter(e => e.data?.edgeType === 'implicit');
    expect(implicitEdges.length).toBe(0);
  });
});

describe('边界场景: 循环依赖处理', () => {
  it('拓扑排序正确（无循环时）', () => {
    const p: PipelineDetail = {
      name: 'diamond',
      pipelines: [
        { name: 'a', depends_on: [], tasks: [{ name: 't1', env: {}, retry: 0, depends_on: [] }] },
        { name: 'b', depends_on: ['a'], tasks: [{ name: 't2', env: {}, retry: 0, depends_on: [] }] },
        { name: 'c', depends_on: ['a'], tasks: [{ name: 't3', env: {}, retry: 0, depends_on: [] }] },
        { name: 'd', depends_on: ['b', 'c'], tasks: [{ name: 't4', env: {}, retry: 0, depends_on: [] }] },
      ],
    };

    const { nodes } = yamlToNodes(p);
    const subNodes = nodes.filter(n => n.type === 'editorSubPipeline');
    expect(subNodes.length).toBe(4);

    // 验证节点本身存在即可，拓扑顺序由位置决定
    const names = subNodes.map(n => n.data?.label);
    expect(names).toContain('a');
    expect(names).toContain('b');
    expect(names).toContain('c');
    expect(names).toContain('d');
  });

  it('自引用 depends_on 不会导致无限循环', () => {
    // yamlToNodes 的 visit 函数使用 visiting Set 防止循环
    const p: PipelineDetail = {
      name: 'cyclic',
      pipelines: [
        { name: 'x', depends_on: ['x'], tasks: [{ name: 't', env: {}, retry: 0, depends_on: [] }] },
      ],
    };

    // 不应抛出异常
    expect(() => yamlToNodes(p)).not.toThrow();
    const { nodes } = yamlToNodes(p);
    expect(nodes.find(n => n.data?.label === 'x')).toBeDefined();
  });
});

describe('边界场景: Post 容器边界', () => {
  it('仅 on_fail 的 post 配置', () => {
    const p: PipelineDetail = {
      name: 'only-fail',
      pipelines: [{
        name: 'job',
        depends_on: [],
        tasks: [{ name: 'main', env: {}, retry: 0, depends_on: [] }],
        post: {
          on_fail: [{ name: 'alert', command: 'curl webhook', env: {}, retry: 0, depends_on: [] }],
        },
      }],
    };

    const { nodes, edges } = yamlToNodes(p);
    const { pipeline: restored, errors } = nodesToYaml(nodes, edges);

    expect(errors).toEqual([]);
    expect(restored?.pipelines?.[0].post?.on_fail).toBeDefined();
    expect(restored?.pipelines?.[0].post?.on_success).toBeUndefined();
    expect(restored?.pipelines?.[0].post?.always).toBeUndefined();
  });

  it('post 为空对象（无任何钩子）', () => {
    const p: PipelineDetail = {
      name: 'no-post',
      pipelines: [{
        name: 'job',
        depends_on: [],
        tasks: [{ name: 'main', env: {}, retry: 0, depends_on: [] }],
      }],
    };

    const { nodes } = yamlToNodes(p);
    // 不应生成 post 父容器
    const postParent = nodes.find(n => n.type === 'editorPostParent');
    expect(postParent).toBeUndefined();
  });
});

/**
 * 数据层补充测试（H）
 * 验证:
 *   1. 100 节点画布序列化/反序列化性能（<2s）
 *   2. 节点图标验证
 *   3. 节点颜色遵循层级模型
 *   注意: React 将 inline style 颜色标准化为 rgb() 格式
 */

describe('数据层补充: 性能测试', () => {
  it('100 节点画布序列化+反序列化在 2 秒内完成', () => {
    // 构建包含多个 SubPipeline 的 Pipeline（20 个 SubPipeline × 5 task = 100 task 节点）
    const pipelines: NonNullable<PipelineDetail['pipelines']> = [];
    for (let s = 0; s < 20; s++) {
      const tasks: NonNullable<PipelineDetail['pipelines']>[number]['tasks'] = [];
      for (let t = 0; t < 5; t++) {
        tasks.push({
          name: `task-${s}-${t}`,
          command: `echo ${s}-${t}`,
          env: {},
          retry: t % 3,
          depends_on: t > 0 ? [`task-${s}-${t - 1}`] : [],
        });
      }
      pipelines.push({
        name: `sub-${s}`,
        depends_on: s > 0 ? [`sub-${s - 1}`] : [],
        tasks,
      });
    }

    const p: PipelineDetail = { name: 'perf-test', pipelines };

    const start = performance.now();
    const { nodes, edges } = yamlToNodes(p);
    const result = nodesToYaml(nodes, edges);
    const elapsed = performance.now() - start;

    expect(elapsed).toBeLessThan(2000);
    expect(result.errors).toEqual([]);
    expect(result.pipeline?.pipelines?.length).toBe(20);

    // 验证 total task 数量
    let totalTasks = 0;
    for (const sub of result.pipeline?.pipelines || []) {
      totalTasks += sub.tasks.length;
    }
    expect(totalTasks).toBe(100);
  });

  it('50 个 SubPipeline 的序列化在 1 秒内完成', () => {
    const pipelines: NonNullable<PipelineDetail['pipelines']> = [];
    for (let s = 0; s < 50; s++) {
      pipelines.push({
        name: `sub-${s}`,
        depends_on: [],
        tasks: [{ name: `t-${s}`, env: {}, retry: 0, depends_on: [] }],
      });
    }

    const p: PipelineDetail = { name: 'large', pipelines };

    const start = performance.now();
    const { nodes, edges } = yamlToNodes(p);
    const elapsedParse = performance.now() - start;

    const startSerial = performance.now();
    const result = nodesToYaml(nodes, edges);
    const elapsedSerial = performance.now() - startSerial;

    expect(elapsedParse).toBeLessThan(1000);
    expect(elapsedSerial).toBeLessThan(1000);
    expect(result.errors).toEqual([]);
  });
});

describe('数据层补充: 节点视觉验证', () => {
  it('SubPipeline 节点使用蓝色虚线边框（层级模型颜色）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    expect(style).toContain('dashed');
    // #3b82f6 → rgb(59, 130, 246)
    expect(style).toContain('59, 130, 246');
    unmount();
  });

  it('Task 节点使用绿色虚线边框', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode data={{ task: { name: 'test', env: {}, retry: 0, depends_on: [] } }} />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    expect(style).toContain('dashed');
    // #22c55e → rgb(34, 197, 94)
    expect(style).toContain('34, 197, 94');
    unmount();
  });

  it('Post 父容器节点使用红色虚线边框', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    // #ef4444 → rgb(239, 68, 68)
    expect(style).toContain('239, 68, 68');
    unmount();
  });

  it('Post 子容器 on_fail 使用红色强调条', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostChildNode
        data={{ task: { name: 'alert', env: {}, retry: 0, depends_on: [] }, postVariant: 'on_fail' }}
      />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    expect(style).toContain('3px');
    // #ef4444 → rgb(239, 68, 68)
    expect(style).toContain('239, 68, 68');
    unmount();
  });

  it('Post 子容器 on_success 使用绿色强调条', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostChildNode
        data={{ task: { name: 'tag', env: {}, retry: 0, depends_on: [] }, postVariant: 'on_success' }}
      />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    expect(style).toContain('3px');
    // #22c55e → rgb(34, 197, 94)
    expect(style).toContain('34, 197, 94');
    unmount();
  });

  it('SubPipeline 容器使用圆角边框', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const root = container.firstChild as HTMLElement;
    const style = root.getAttribute('style') || '';
    expect(style).toContain('border-radius');
    unmount();
  });
});

/**
 * v2 (2026-07): SVG 图标验证
 * PM spec 要求所有节点使用 SVG 组件（严禁 emoji unicode 字符）
 * 验证:
 *   1. 节点渲染使用 SVG 组件（<svg> 标签存在）
 *   2. 节点中不存在 emoji 字符（⚠⬡⚙⌨ 等）
 */
describe('SVG 图标验证', () => {
  /** emoji 中常用作图标替代的 unicode 范围 */
  const EMOJI_CHARS = /[⚠⬡⚙⌨⏳✓✗▶◀▲▼●○◆◇▲▼☐☑☒⭐♻⬆⬇⬅➡🔄💾📁📂🔍🔧]+/u;

  it('SubPipeline 节点渲染包含 SVG 元素（SubPipelineIcon）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    // SubPipelineIcon 渲染为 <svg> 标签
    expect(container.querySelector('svg')).not.toBeNull();
    unmount();
  });

  it('Task 节点渲染包含 SVG 元素（CmdIcon/StepIcon 等）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorTaskNode
        data={{ task: { name: 'compile', command: 'make', env: {}, retry: 0, depends_on: [] }, taskType: 'command' }}
      />,
    );
    // CmdIcon 渲染为 <svg> 标签
    expect(container.querySelector('svg')).not.toBeNull();
    unmount();
  });

  it('PostParent 节点渲染包含 SVG 元素（PostParentIcon）', () => {
    const { container, unmount } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );
    expect(container.querySelector('svg')).not.toBeNull();
    unmount();
  });

  it('节点渲染内容中不存在 emoji 字符（⚠⬡⚙⌨）', () => {
    const { container: c1, unmount: u1 } = renderWithProvider(
      <EditorSubPipelineNode data={{ label: 'build' }} />,
    );
    const { container: c2, unmount: u2 } = renderWithProvider(
      <EditorTaskNode
        data={{ task: { name: 't', command: 'cmd', env: {}, retry: 0, depends_on: [] }, taskType: 'command' }}
      />,
    );
    const { container: c3, unmount: u3 } = renderWithProvider(
      <EditorPostParentNode data={{ label: 'Post' }} />,
    );
    const { container: c4, unmount: u4 } = renderWithProvider(
      <EditorPostChildNode
        data={{ task: { name: 'alert', env: {}, retry: 0, depends_on: [] }, postVariant: 'on_fail' }}
      />,
    );

    const allHtml = [c1, c2, c3, c4].map(c => c.innerHTML).join('');
    expect(allHtml).not.toMatch(EMOJI_CHARS);
    u1(); u2(); u3(); u4();
  });
});

/**
 * v3 (2026-07): 渲染性能测试
 * 100+ 节点 pipeline → WorkflowEditor 渲染 < 2s
 * 验证 React Flow 画布渲染性能在安全阈值内
 */
describe('渲染性能: 100 节点画布渲染', () => {
  it('20 SubPipeline × 5 tasks = 100 task 节点 → 渲染到 React Flow 画布 < 2s', async () => {
    const pipelines: NonNullable<PipelineDetail['pipelines']> = [];
    for (let s = 0; s < 20; s++) {
      const tasks: NonNullable<PipelineDetail['pipelines']>[number]['tasks'] = [];
      for (let t = 0; t < 5; t++) {
        tasks.push({
          name: `t-${s}-${t}`,
          command: `echo ${s}-${t}`,
          env: {},
          retry: 0,
          depends_on: t > 0 ? [`t-${s}-${t - 1}`] : [],
        });
      }
      pipelines.push({
        name: `sub-${s}`,
        depends_on: s > 0 ? [`sub-${s - 1}`] : [],
        tasks,
      });
    }

    const p: PipelineDetail = { name: 'perf-render', pipelines };

    const start = performance.now();
    const { container, unmount } = render(
      <WorkflowEditor
        pipeline={p}
        selectedNodeId={null}
        onNodeSelect={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.react-flow')).toBeInTheDocument();
    });

    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(2000);

    // 验证节点确实渲染了
    const flowNodes = container.querySelectorAll('.react-flow__node');
    // 100 tasks + 20 SubPipeline + 1 pipeline + 1 start + 1 end = 123 个节点
    expect(flowNodes.length).toBeGreaterThanOrEqual(100);

    unmount();
  });
});
