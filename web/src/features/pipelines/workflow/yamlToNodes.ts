import type { Node, Edge, XYPosition } from '@xyflow/react';
import { MarkerType } from '@xyflow/react';
import type { PipelineDetail, PipelineConfig, TaskYAML, TaskType } from '@/types';

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

const GAP_X = 60;
const GAP_Y = 80;
const NODE_W = 180;
const NODE_H = 56;
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
    let currentX = CONTAINER_PADDING;
    let currentY = CONTAINER_PADDING;

    // 先创建所有 SubPipeline 节点
    for (const subName of subpipelineOrder) {
      const sub = subpipelines.find(s => s.name === subName)!;
      const subId = `__pipeline__${sub.name}`;
      const strategy = resolveStrategy(sub.config, topOptions);

      const taskCount = (sub.tasks || []).length;
      // 动态计算容器高度
      const containerH = CONTAINER_PADDING * 2 +
        taskCount * (NODE_H + GAP_Y) + 40;

      nodes.push({
        id: subId,
        type: 'editorSubPipeline',
        parentId: pipelineId,
        position: { x: currentX, y: currentY },
        style: { width: NODE_W + CONTAINER_PADDING * 2, height: Math.max(140, containerH) },
        data: {
          label: sub.name,
          executionStrategy: strategy,
          maxConcurrentTasks: sub.config?.max_concurrent_tasks ?? topOptions?.max_concurrent_tasks ?? undefined,
        },
      });

      currentX += (NODE_W + CONTAINER_PADDING * 2) + GAP_X;
    }

    // 创建 Task 节点
    for (const sub of subpipelines) {
      const subId = `__pipeline__${sub.name}`;
      const strategy = resolveStrategy(sub.config, topOptions);

      const tasks = sub.tasks || [];
      for (let i = 0; i < tasks.length; i++) {
        const task = tasks[i];
        const taskId = `__task__${sub.name}.${task.name}`;

        nodes.push({
          id: taskId,
          type: 'editorTask',
          parentId: subId,
          position: { x: CONTAINER_PADDING, y: CONTAINER_PADDING + 40 + i * (NODE_H + GAP_Y) },
          data: {
            task,
            taskType: inferType(task),
            subpipelineName: sub.name,
          },
        });

        // depends_on 显式边
        for (const dep of task.depends_on || []) {
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

        // 隐式边（sequential 且没有显式 depends_on 时）
        if (i > 0 && strategy !== 'parallel') {
          const prevTask = tasks[i - 1];
          const existingDep = (task.depends_on || []).includes(prevTask.name);
          if (!existingDep) {
            const prevTaskId = `__task__${sub.name}.${prevTask.name}`;
            edges.push({
              id: `__edge__implicit_${sub.name}.${prevTask.name}_to_${sub.name}.${task.name}`,
              source: prevTaskId,
              target: taskId,
              type: 'smoothstep',
              markerEnd: { type: MarkerType.ArrowClosed, width: 8, height: 8, color: '#cbd5e1' },
              style: { stroke: '#cbd5e1', strokeWidth: 1.5, strokeDasharray: '3 3' },
              data: {
                edgeType: 'implicit',
                subpipelineName: sub.name,
                sourceTask: prevTask.name,
                targetTask: task.name,
                explicit: false,
                implicit: true,
              },
            });
          }
        }
      }

      // === Post 处理 ===
      if (sub.post && (sub.post.on_fail?.length || sub.post.on_success?.length || sub.post.always?.length)) {
        const postParentId = `__post__${subId}_parent`;

        nodes.push({
          id: postParentId,
          type: 'editorPostParent',
          parentId: pipelineId,
          position: { x: 0, y: 0 }, // 会在连接后由布局调整
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
              position: { x: CONTAINER_PADDING, y: CONTAINER_PADDING + childIdx * (NODE_H + GAP_Y) },
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
    for (const sub of subpipelines) {
      for (const dep of sub.depends_on || []) {
        const sourceTasks = subpipelines.find(s => s.name === dep)?.tasks || [];
        const targetTasks = sub.tasks || [];

        if (sourceTasks.length > 0 && targetTasks.length > 0) {
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

  // === 调整 Pipeline 容器大小以包裹所有子节点 ===
  const pipelineChildren = nodes.filter(n => n.parentId === pipelineId);
  if (pipelineChildren.length > 0) {
    let maxX = 0, maxY = 0;
    for (const child of pipelineChildren) {
      const childW = (child.style as { width?: number })?.width ?? NODE_W;
      const childH = (child.style as { height?: number })?.height ?? NODE_H;
      const right = child.position.x + (typeof childW === 'number' ? childW : 0);
      const bottom = child.position.y + (typeof childH === 'number' ? childH : 0);
      maxX = Math.max(maxX, right);
      maxY = Math.max(maxY, bottom);
    }
    const pNode = nodes.find(n => n.id === pipelineId);
    if (pNode) {
      pNode.style = {
        width: maxX + CONTAINER_PADDING + 100,
        height: maxY + CONTAINER_PADDING + 100,
      };
    }
  }

  return { nodes, edges };
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
