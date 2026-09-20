import type { Node, Edge } from '@xyflow/react';
import type { PipelineDetail, PipelineConfig, TaskYAML, TaskType, PostConfig, ArtifactDeclaration } from '@/types';
import { editorEdgeVisual, type EditorEdgeKind } from './edgeStyles';
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
  /**
   * v7 (2026-08): 画布无法可视化编辑顶层 post/artifacts 与 subpipeline.artifacts，
   * 暂存在容器节点 data 中，序列化时原样回填，避免「进编辑模式保存一次就丢」
   */
  post?: PostConfig | null;
  artifacts?: ArtifactDeclaration[];
  /**
   * v7 (2026-08): 暂存完整 config —— 画布只编辑 execution_strategy/max_concurrent_tasks，
   * 旧实现重建 config 时用 env:{}/retry:0/on_failure:'stop' 覆盖，会把 env 变量、
   * timeout、retry、on_failure 等字段静默清空
   */
  config?: PipelineConfig | null;
  /** 顶层 config 原始挂在 config 还是 options 字段，序列化时写回原字段 */
  configField?: 'config' | 'options' | null;
  /** 顶层 options 原始值（config 存在时 options 仍要原样保留，避免画布保存抹掉） */
  options?: PipelineConfig | null;
  [key: string]: unknown;
}

/**
 * v11 (2026-08): bezier 边类型（'default'）
 * 为什么不再是 smoothstep：LR 流向下 bezier 才是 n8n 标志性顺流曲线；
 * bezier 无 pathOptions 特化，普通 Edge 类型即可
 */
export type EditorEdge = Edge<EditorEdgeData>;

// v11 (2026-08): 与 nodeTokens.NODE_SIZE 对齐（任务卡 200×56），LR 横向节奏
// 导出供 editorAutoLayout 复用，避免两处硬编码漂移
export const EDITOR_LAYOUT = {
  GAP_X: 48,
  GAP_Y: 40,
  NODE_W: 200,
  NODE_H: 56,
  CONTAINER_PADDING: 32,
  /** header 行高度（组名/策略/任务数），任务区从其下方开始 */
  HEADER_H: 36,
  // v11: 哨兵与容器的水平间距 —— 给贝塞尔曲线足够的呼吸空间
  SENTINEL_GAP: 72,
  SENTINEL_START_W: 112,
  SENTINEL_END_W: 96,
  SENTINEL_H: 56,
} as const;
const {
  GAP_X,
  GAP_Y,
  NODE_W,
  NODE_H,
  CONTAINER_PADDING,
  HEADER_H,
  SENTINEL_GAP,
  SENTINEL_START_W,
  SENTINEL_H,
} = EDITOR_LAYOUT;

/**
 * v9 (2026-08): 构造一条编辑器边（样式统一从 edgeStyles 工厂取）
 * 为什么封装：旧版每处边都手写 markerEnd+style，颜色错配/虚线噪音即源于此
 * v11 (2026-08): bezier 无箭头 —— 工厂只返回 type+style
 */
function makeEdge(params: {
  id: string;
  source: string;
  target: string;
  kind: EditorEdgeKind;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  data: EditorEdgeData;
}): EditorEdge {
  const { type, style } = editorEdgeVisual(params.kind);
  return {
    id: params.id,
    source: params.source,
    target: params.target,
    sourceHandle: params.sourceHandle ?? null,
    targetHandle: params.targetHandle ?? null,
    type,
    style,
    data: params.data,
  };
}

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

  // v7 (2026-08): 与后端 PipelineYAML.get_effective_config 对齐 —— config 优先于 options。
  // 旧实现 options 优先，config+options 并存时画布展示的策略与实际执行不一致。
  const topOptions = pipeline.config ?? pipeline.options ?? null;

  // === Start 节点（position 在布局后调整到根容器左侧） ===
  nodes.push({
    id: '__start__',
    type: 'editorStartEnd',
    position: { x: 0, y: 0 },
    data: { variant: 'start' },
  });

  // === End 节点（position 在布局后调整到根容器右侧） ===
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
      // v7 (2026-08): 暂存顶层 post/artifacts 与完整 config，供 nodesToYaml 回填
      post: pipeline.post ?? null,
      artifacts: pipeline.artifacts ?? [],
      config: topOptions ?? null,
      configField: pipeline.config ? 'config' : pipeline.options ? 'options' : null,
      options: pipeline.options ?? null,
    },
  });

  // START → Pipeline（绿色入口语义，与查看模式图例一致）
  // v11: 显式 handle（out→in）—— 根容器有 out/post 两个 source handle，
  // 缺省 handle 依赖渲染顺序不可靠
  edges.push(makeEdge({
    id: `__edge__start_to_pipeline`,
    source: '__start__',
    target: pipelineId,
    sourceHandle: 'out',
    targetHandle: 'in',
    kind: 'start',
    data: { edgeType: 'cross_container', explicit: true, implicit: false },
  }));

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

    // === 布局计算（v11 LR：SubPipeline 容器横排成行，任务在容器内横排成链） ===
    let currentX = CONTAINER_PADDING;
    const SUB_ROW_Y = CONTAINER_PADDING;

    // 先创建所有 SubPipeline 节点（记录容器几何，供 Post 容器与哨兵定位）
    const subGeometry = new Map<string, { x: number; w: number; h: number }>();
    for (const subName of subpipelineOrder) {
      const sub = subpipelines.find(s => s.name === subName)!;
      const subId = `__pipeline__${sub.name}`;
      const strategy = resolveStrategy(sub.config, topOptions);

      const taskCount = (sub.tasks || []).length;
      // v11 (LR): 容器宽度 = 任务链横向长度（单行），高度只含 header + 一行任务
      const containerW = Math.max(
        240,
        CONTAINER_PADDING * 2 + taskCount * NODE_W + Math.max(0, taskCount - 1) * GAP_X,
      );
      const containerH = HEADER_H + 16 + NODE_H + 24;

      nodes.push({
        id: subId,
        type: 'editorSubPipeline',
        parentId: pipelineId,
        position: { x: currentX, y: SUB_ROW_Y },
        style: { width: containerW, height: containerH },
        data: {
          label: sub.name,
          executionStrategy: strategy,
          maxConcurrentTasks: sub.config?.max_concurrent_tasks ?? topOptions?.max_concurrent_tasks ?? undefined,
          // v7 (2026-08): 暂存 subpipeline.artifacts 与完整 config，供 nodesToYaml 回填
          artifacts: sub.artifacts ?? [],
          config: sub.config ?? null,
        },
      });

      subGeometry.set(subId, { x: currentX, w: containerW, h: containerH });
      currentX += containerW + GAP_X;
    }

    // 创建 Task 节点（容器内横向链式排布）
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
          // v11 (LR): 任务横向成链 —— x 递增（流向），y 在任务区垂直居中
          // （handle 左入右出，同链任务直线贯穿）
          position: {
            x: CONTAINER_PADDING + i * (NODE_W + GAP_X),
            y: HEADER_H + 16,
          },
          // 固定节点尺寸 —— 内容自适应宽度会让同链任务的 handle 错位
          style: { width: NODE_W, height: NODE_H },
          data: {
            task,
            taskType: inferType(task),
            subpipelineName: sub.name,
          },
        });

        // depends_on 显式边
        for (const dep of task.depends_on || []) {
          edges.push(makeEdge({
            id: `__edge__${sub.name}.${dep}_to_${sub.name}.${task.name}`,
            source: `__task__${sub.name}.${dep}`,
            target: taskId,
            kind: 'rail',
            data: {
              edgeType: 'explicit',
              subpipelineName: sub.name,
              sourceTask: dep,
              targetTask: task.name,
              explicit: true,
              implicit: false,
            },
          }));
        }

        // 隐式边（sequential 且没有显式 depends_on 时）
        if (i > 0 && strategy !== 'parallel') {
          const prevTask = tasks[i - 1];
          const existingDep = (task.depends_on || []).includes(prevTask.name);
          if (!existingDep) {
            const prevTaskId = `__task__${sub.name}.${prevTask.name}`;
            edges.push(makeEdge({
              id: `__edge__implicit_${sub.name}.${prevTask.name}_to_${sub.name}.${task.name}`,
              source: prevTaskId,
              target: taskId,
              kind: 'implicit',
              data: {
                edgeType: 'implicit',
                subpipelineName: sub.name,
                sourceTask: prevTask.name,
                targetTask: task.name,
                explicit: false,
                implicit: true,
              },
            }));
          }
        }
      }

      // === Post 处理 ===
      if (sub.post && (sub.post.on_fail?.length || sub.post.on_success?.length || sub.post.always?.length)) {
        const postParentId = `__post__${subId}_parent`;
        // v11 (LR): Post 容器挂在其源 SubPipeline 正下方（post 端口在容器底部，
        // 下行短曲线即达；旧版 (0,0) 从未真正被调整，Post 容器堆在根容器左上角）
        const geo = subGeometry.get(subId);
        const subRowBottom = Math.max(...Array.from(subGeometry.values()).map(g => g.h)) + SUB_ROW_Y;

        nodes.push({
          id: postParentId,
          type: 'editorPostParent',
          parentId: pipelineId,
          position: { x: geo?.x ?? CONTAINER_PADDING, y: subRowBottom + 40 },
          style: { width: 280, height: 200 },
          data: { label: `${sub.name} Post`, parentTaskId: subId },
        });

        // Post 连接边: sub_container → post_parent
        edges.push(makeEdge({
          id: `__edge__post_${subId}_to_${postParentId}`,
          source: subId,
          sourceHandle: 'post',
          target: postParentId,
          kind: 'post',
          data: { edgeType: 'post_routing', explicit: true, implicit: false },
        }));

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
          edges.push(makeEdge({
            id: `__edge__cross_pipeline_${dep}_${sub.name}`,
            source: `__pipeline__${dep}`,
            sourceHandle: 'out',
            target: `__pipeline__${sub.name}`,
            targetHandle: 'in',
            kind: 'cross',
            data: { edgeType: 'cross_container', explicit: true, implicit: false },
          }));
        }
      }
    }
  }

  // Pipeline → End（主流轨灰，显式 handle）
  edges.push(makeEdge({
    id: `__edge__pipeline_to_end`,
    source: pipelineId,
    sourceHandle: 'out',
    target: '__end__',
    targetHandle: 'in',
    kind: 'rail',
    data: { edgeType: 'cross_container', explicit: true, implicit: false },
  }));

  // v11 (2026-08): LR 定位 —— START 在根容器左侧、END 在右侧（水平流向的哨兵位），
  // 旧布局 START 在正上/END 在正下（TB 流向遗产）
  const startNode = nodes.find(n => n.id === '__start__');
  const endNode = nodes.find(n => n.id === '__end__');
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
      const rootW = maxX + CONTAINER_PADDING;
      const rootH = maxY + CONTAINER_PADDING;
      pNode.style = { width: rootW, height: rootH };
      // v11 (LR): START 贴根容器左侧垂直居中、END 贴右侧垂直居中 ——
      // in/out handle 均在左右缘中点，跨容器边短且顺流
      if (startNode) {
        startNode.position = { x: -SENTINEL_START_W - SENTINEL_GAP, y: rootH / 2 - SENTINEL_H / 2 };
      }
      if (endNode) {
        endNode.position = { x: rootW + SENTINEL_GAP, y: rootH / 2 - SENTINEL_H / 2 };
      }
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
