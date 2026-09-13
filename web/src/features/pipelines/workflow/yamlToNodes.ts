import type { Node, Edge } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { PipelineDetail, PipelineConfig, TaskYAML, TaskType } from '@/types';
import { layoutGraph } from './layoutGraph';
import { normalizeTopLevelTasks } from '@/utils/normalizePipeline';

/**
 * YAML (PipelineDetail) → React Flow nodes + edges 反序列化
 * 将后端数据模型转换为可编辑画布上的节点和边
 *
 * 节点 ID 命名规则（确保确定性，便于双向同步）:
 *   __start__ ── Start 哨兵
 *   __end__   ── End 哨兵
 *   __pipeline__        ── 根 Pipeline 容器
 *   __pipeline__<name>  ── SubPipeline 容器
 *   __task__<sub>.<name> ── Task 容器
 *   __post__<parentId>_<hook> ── Post 父容器
 *   __postchild__<parentPostId>_<hook>_<idx> ── Post 子容器
 *
 * 边数据扩展:
 *   data.edgeType: 'explicit' | 'implicit' | 'post_routing'
 *   data.subpipelineName / data.sourceTask / data.targetTask: 用于序列化
 */

export interface EditorEdgeData {
  edgeType: 'explicit' | 'implicit' | 'post_routing' | 'cross_container';
  subpipelineName?: string;
  sourceTask?: string;
  targetTask?: string;
  explicit: boolean;
  implicit: boolean;
  [key: string]: unknown;
}

export interface EditorNodeData {
  label?: string;
  task?: TaskYAML;
  taskType?: TaskType;
  subpipelineName?: string;
  executionStrategy?: string;
  maxConcurrentTasks?: number;
  postVariant?: 'on_fail' | 'on_success' | 'always';
  parentTaskId?: string;
  variant?: 'start' | 'end';
  [key: string]: unknown;
}

const NODE_W = 180;
const CONTAINER_PADDING = 40;

/** 推断任务类型 */
function inferType(task: TaskYAML): TaskType {
  if (task.invoke) return 'invoke';
  if (task.steps) return 'steps';
  if (task.plugin) return 'plugin';
  if (task.git) return 'git';
  if (task.nexus) return 'nexus';
  return 'command';
}

/** 推导 execution_strategy（含继承） */
function resolveStrategy(config: PipelineConfig | null | undefined, topOptions: PipelineConfig | null | undefined): string {
  if (config?.execution_strategy) return config.execution_strategy;
  if (topOptions?.execution_strategy) return topOptions.execution_strategy;
  return 'sequential';
}

export interface YamlToNodesResult {
  nodes: Node<EditorNodeData>[];
  edges: Edge<EditorEdgeData>[];
}

/**
 * 将 PipelineDetail 转换为 React Flow 可编辑节点和边
 *
 * @param pipeline 后端 PipelineDetail 数据
 * @returns 包含节点数组和边数组的结果
 */
export function yamlToNodes(pipeline: PipelineDetail): YamlToNodesResult {
  // v3 (2026-07): 与后端 _normalize 对齐，顶层 tasks 统一包装为同名 SubPipeline。
  // 放在渲染入口而不是只放在 parse 层，保证所有调用方（API 数据/YAML 解析/测试构造）
  // 的渲染行为一致，避免"某入口能看到任务、某入口看不到"。
  pipeline = normalizeTopLevelTasks(pipeline);

  const nodes: Node<EditorNodeData>[] = [];
  const edges: Edge<EditorEdgeData>[] = [];

  const topOptions = pipeline.options ?? pipeline.config ?? null;

  // === Start 节点（固定位置 0,0） ===
  nodes.push({
    id: '__start__',
    type: 'editorStartEnd',
    position: { x: 0, y: 0 },
    data: { variant: 'start' },
  });

  // === End 节点（position 在布局后调整） ===
  nodes.push({
    id: '__end__',
    type: 'editorStartEnd',
    position: { x: 800, y: 600 },
    data: { variant: 'end' },
  });

  // === Pipeline 根容器 ===
  const pipelineId = '__pipeline__';
  nodes.push({
    id: pipelineId,
    type: 'editorPipeline',
    position: { x: 0, y: 0 },
    style: { width: 800, height: 400 },
    data: {
      label: pipeline.name,
      executionStrategy: resolveStrategy(topOptions, null),
      maxConcurrentTasks: topOptions?.max_concurrent_tasks ?? undefined,
    },
  });

  // START → Pipeline
  edges.push({
    id: `__edge__start_to_pipeline`,
    source: '__start__',
    target: pipelineId,
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#10B981' },
    style: { stroke: '#10B981', strokeWidth: 1.5 },
    data: { edgeType: 'cross_container', explicit: true, implicit: false },
  });

  const subpipelines = pipeline.pipelines || [];
  const subpipelineOrder: string[] = []; // 拓扑序

  if (subpipelines.length > 0) {
    // === 拓扑排序 SubPipeline ===
    const visited = new Set<string>();
    const visiting = new Set<string>();
    const order: string[] = [];

    function visit(name: string) {
      if (visited.has(name)) return;
      if (visiting.has(name)) return; // 简单处理循环
      visiting.add(name);
      const sub = subpipelines.find(s => s.name === name);
      if (sub?.depends_on) {
        for (const dep of sub.depends_on) {
          visit(dep);
        }
      }
      visiting.delete(name);
      visited.add(name);
      order.push(name);
    }

    for (const sub of subpipelines) {
      visit(sub.name);
    }
    subpipelineOrder.push(...order);

    // === 布局计算 ===
    // 位置交给统一的容器感知布局 layoutGraph 计算（见文件末尾），
    // 这里只构建结构，初始 position 统一 {0,0}，避免两套布局算法互相打架。

    // 先创建所有 SubPipeline 节点
    for (const subName of subpipelineOrder) {
      const sub = subpipelines.find(s => s.name === subName)!;
      const subId = `__pipeline__${sub.name}`;
      const strategy = resolveStrategy(sub.config, topOptions);

      nodes.push({
        id: subId,
        type: 'editorSubPipeline',
        parentId: pipelineId,
        position: { x: 0, y: 0 },
        style: { width: NODE_W + CONTAINER_PADDING * 2, height: 140 },
        data: {
          label: sub.name,
          executionStrategy: strategy,
          maxConcurrentTasks: sub.config?.max_concurrent_tasks ?? topOptions?.max_concurrent_tasks ?? undefined,
        },
      });
    }

    // 创建 Task 节点
    for (const sub of subpipelines) {
      const subId = `__pipeline__${sub.name}`;
      const strategy = resolveStrategy(sub.config, topOptions);

      const tasks = sub.tasks || [];
      // v2 (2026-07): 数据健壮性 —— 同容器重名任务会生成重复节点 ID，
      // 直接击穿 React key 约束并让布局位置互相覆盖；depends_on 引用不存在的任务
      // 会生成悬空边（React Flow 无法渲染）。这里在反序列化层做最小容错：
      // 重名任务只保留第一个，depends_on 只对存在的任务建边。
      const validTaskNames = new Set(tasks.map((t) => t.name));
      const renderedTaskNames = new Set<string>();
      let lastRenderedTaskName: string | null = null;

      for (let i = 0; i < tasks.length; i++) {
        const task = tasks[i];

        if (renderedTaskNames.has(task.name)) {
          // 重名任务：跳过渲染并显式告警，避免画布静默损坏
          console.warn(
            `[yamlToNodes] SubPipeline "${sub.name}" 存在重名任务 "${task.name}"，已跳过重复项`,
          );
          continue;
        }
        renderedTaskNames.add(task.name);

        const taskId = `__task__${sub.name}.${task.name}`;

        nodes.push({
          id: taskId,
          type: 'editorTask',
          parentId: subId,
          position: { x: 0, y: 0 },
          // v2 (2026-07): 显式尺寸必须与 layoutGraph 的默认估算一致。
          // 否则节点在浏览器中由内容自适应宽度（when 标签/长名称会撑宽），
          // 初始布局按 180 估算会导致子节点越出容器（e2e 实测暴露）。
          style: { width: 180, height: 56 },
          data: {
            task,
            taskType: inferType(task),
            subpipelineName: sub.name,
          },
        });

        // depends_on 显式边 —— 仅当被依赖任务存在时创建，避免悬空边
        // v3 (2026-07): 去重 + 跳过自依赖 —— 重复依赖会生成相同边 ID（React key 冲突），
        // 自依赖会生成自环边（执行引擎同样将其视为非法环）
        const seenDeps = new Set<string>();
        for (const dep of task.depends_on || []) {
          if (dep === task.name || seenDeps.has(dep)) continue;
          seenDeps.add(dep);
          if (!validTaskNames.has(dep)) continue;
          edges.push({
            id: `__edge__${sub.name}.${dep}_to_${sub.name}.${task.name}`,
            source: `__task__${sub.name}.${dep}`,
            target: taskId,
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed, width: 8, height: 8, color: '#94a3b8' },
            style: { stroke: '#94a3b8', strokeWidth: 2 },
            data: {
              edgeType: 'explicit',
              subpipelineName: sub.name,
              sourceTask: dep,
              targetTask: task.name,
              explicit: true,
              implicit: false,
            },
          });
        }

        // 隐式边（sequential 且任务没有任何显式 depends_on 时）
        // v2 (2026-07): 与执行引擎语义对齐（server/taskpps/domain/dag.py:30 — 仅当
        // depends_on 为空才补充"依赖前一个任务"）。原实现只要前一个任务不在
        // depends_on 里就补边，会把菱形依赖渲染成串行长链（截图/压测暴露）。
        // 注意用 lastRenderedTaskName：重名跳过时 tasks[i-1] 可能未渲染
        if (lastRenderedTaskName !== null && strategy !== 'parallel') {
          const hasExplicitDeps = (task.depends_on?.length ?? 0) > 0;
          if (!hasExplicitDeps) {
            edges.push({
              id: `__edge__implicit_${sub.name}.${lastRenderedTaskName}_to_${sub.name}.${task.name}`,
              source: `__task__${sub.name}.${lastRenderedTaskName}`,
              target: taskId,
              type: 'smoothstep',
              markerEnd: { type: MarkerType.ArrowClosed, width: 8, height: 8, color: '#cbd5e1' },
              style: { stroke: '#cbd5e1', strokeWidth: 1.5, strokeDasharray: '3 3' },
              data: {
                edgeType: 'implicit',
                subpipelineName: sub.name,
                sourceTask: lastRenderedTaskName,
                targetTask: task.name,
                explicit: false,
                implicit: true,
              },
            });
          }
        }

        lastRenderedTaskName = task.name;
      }

      // === Post 处理 ===
      if (sub.post && (sub.post.on_fail?.length || sub.post.on_success?.length || sub.post.always?.length)) {
        const postParentId = `__post__${subId}_parent`;

        nodes.push({
          id: postParentId,
          type: 'editorPostParent',
          parentId: pipelineId,
          position: { x: 0, y: 0 },
          style: { width: 280, height: 200 },
          data: { label: `${sub.name} Post`, parentTaskId: subId },
        });

        // Post 连接边: sub_container → post_parent
        edges.push({
          id: `__edge__post_${subId}_to_${postParentId}`,
          source: subId,
          sourceHandle: 'post',
          target: postParentId,
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed, width: 8, height: 8, color: '#ef4444' },
          style: { stroke: '#ef4444', strokeWidth: 2, strokeDasharray: '4 3' },
          data: { edgeType: 'post_routing', explicit: true, implicit: false },
        });

        let childIdx = 0;
        for (const hookType of ['on_fail', 'on_success', 'always'] as const) {
          const hookTasks = sub.post[hookType];
          if (!hookTasks || hookTasks.length === 0) continue;

          for (const pt of hookTasks) {
            const childId = `__postchild__${postParentId}_${hookType}_${childIdx}`;
            childIdx++;

            nodes.push({
              id: childId,
              type: 'editorPostChild',
              parentId: postParentId,
              position: { x: 0, y: 0 },
              // v2 (2026-07): 与 layoutGraph 默认估算一致，避免内容撑宽导致越界
              style: { width: 180, height: 56 },
              data: {
                task: pt,
                taskType: inferType(pt),
                postVariant: hookType,
                parentTaskId: postParentId,
              },
            });
          }
        }
      }
    }

    // 跨 SubPipeline depends_on 边
    // v2 (2026-07): 去掉"源/目标容器都必须有任务"的限制 —— 空容器同样表达顺序依赖，
    // 否则空容器与下游容器的先后关系在布局中丢失（压力测试暴露：normal 不再排在 empty-one 下方）。
    // v3 (2026-07): 去重 + 跳过自依赖，避免重复边 ID 与容器自环边。
    for (const sub of subpipelines) {
      const seenSubDeps = new Set<string>();
      for (const dep of sub.depends_on || []) {
        if (dep === sub.name || seenSubDeps.has(dep)) continue;
        seenSubDeps.add(dep);
        const depExists = subpipelines.some(s => s.name === dep);
        if (depExists) {
          edges.push({
            id: `__edge__cross_pipeline_${dep}_${sub.name}`,
            source: `__pipeline__${dep}`,
            sourceHandle: 'out',
            target: `__pipeline__${sub.name}`,
            targetHandle: 'in',
            type: 'smoothstep',
            markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#f59e0b' },
            style: { stroke: '#f59e0b', strokeWidth: 1.5, strokeDasharray: '4 3' },
            data: { edgeType: 'cross_container', explicit: true, implicit: false },
          });
        }
      }
    }
  }

  // Pipeline → End
  edges.push({
    id: `__edge__pipeline_to_end`,
    source: pipelineId,
    sourceHandle: 'out',
    target: '__end__',
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 10, height: 10, color: '#94A3B8' },
    style: { stroke: '#94A3B8', strokeWidth: 1.5 },
    data: { edgeType: 'cross_container', explicit: true, implicit: false },
  });

  // === 统一布局 ===
  // 结构构建完成后交给容器感知布局，初始加载与"自动布局"按钮结果一致，
  // 避免两套布局算法造成模式切换时的位置跳变。
  const laidOutNodes = layoutGraph(nodes, edges);

  return { nodes: laidOutNodes, edges };
}

/**
 * 将画布 nodes/edges 反向推导出节点间层级关系
 * 用于 nodesToYAML 序列化时确定 parent 关系
 *
 * @returns { subNames, tasksBySub } 子流水线名列表及各子流水线下的 task 列表
 */
export function extractYamlStructure(nodes: Node<EditorNodeData>[], _edges: Edge<EditorEdgeData>[]): {
  subNames: string[];
  tasksBySub: Map<string, string[]>;
} {
  const subNames: string[] = [];
  const tasksBySub = new Map<string, string[]>();

  for (const node of nodes) {
    if (node.type === 'editorSubPipeline' && node.data?.label) {
      subNames.push(node.data.label);
    }
    if (node.type === 'editorTask' && node.data?.subpipelineName && node.data?.task?.name) {
      const subName = node.data.subpipelineName;
      if (!tasksBySub.has(subName)) tasksBySub.set(subName, []);
      tasksBySub.get(subName)!.push(node.data.task.name);
    }
  }

  return { subNames, tasksBySub };
}
