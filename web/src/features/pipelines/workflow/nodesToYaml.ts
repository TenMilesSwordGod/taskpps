import type { Node, Edge } from '@xyflow/react';
import type { PipelineDetail, TaskYAML, SubPipeline, PostConfig } from '@/types';
import type { EditorNodeData, EditorEdgeData } from './yamlToNodes';

/**
 * React Flow nodes + edges → PipelineDetail 序列化
 * 将可编辑画布上的节点和边转换回后端 YAML 数据模型
 *
 * 处理逻辑:
 *   1. 按 parentId 结构解析 Task 归属的 SubPipeline
 *   2. 同容器 task→task 边 → depends_on
 *   3. 跨容器边（task/sub 之间）→ target SubPipeline 的 depends_on（后端不支持任务级跨容器依赖）
 *   4. 根级 task → 包装为以流水线名命名的隐式 SubPipeline（与后端 _normalize 对齐）
 *   5. 收集 Post 父容器 → Post 子容器关系
 *   6. 无法映射的连线（如 START→END 直连）显式报错，绝不静默丢数据
 *
 * 注意: 隐式边不参与序列化（它们由 execution_strategy 运行时决定）
 *
 * v3 (2026-07): 重大修复 ——
 *   - 原实现依赖 data.subpipelineName 分组，但拖拽新增的 task 该字段恒为空，
 *     保存时任务静默丢失；改为沿 parentId 链解析真实归属
 *   - 跨容器手动连线此前被静默丢弃，现映射为 sub 级依赖
 *   - 根级 task 此前直接报错"所有 Task 必须位于 SubPipeline 内"，现支持保存
 */

export interface SerializationResult {
  pipeline: PipelineDetail | null;
  errors: string[];
}

/**
 * 从小写 postVariant 转换为 PostConfig key
 */
function postVariantToKey(variant: string): 'on_fail' | 'on_success' | 'always' | null {
  if (variant === 'on_fail') return 'on_fail';
  if (variant === 'on_success') return 'on_success';
  if (variant === 'always') return 'always';
  return null;
}

/**
 * 从 nodes + edges 重建 PipelineDetail
 *
 * @param nodes React Flow 节点数组
 * @param edges React Flow 边数组
 * @returns 序列化结果，包含 PipelineDetail 或错误信息列表
 */
export function nodesToYaml(
  nodes: Node<EditorNodeData>[],
  edges: Edge<EditorEdgeData>[],
): SerializationResult {
  const errors: string[] = [];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // === 查找根 Pipeline 名称 ===
  const pipelineNode = nodes.find(n => n.id === '__pipeline__' || n.type === 'editorPipeline');
  const pipelineName = (pipelineNode?.data?.label as string) || 'unnamed';

  // === 收集节点 ===
  const subPipelineNodes = nodes.filter(n => n.type === 'editorSubPipeline');
  const taskNodes = nodes.filter(n => n.type === 'editorTask');
  const postParentNodes = nodes.filter(n => n.type === 'editorPostParent');
  const postChildNodes = nodes.filter(n => n.type === 'editorPostChild');

  /**
   * 沿 parentId 链解析节点归属的 SubPipeline 名。
   * start/end/pipeline 返回 null；task 找到最近的祖先 SubPipeline；
   * 无容器祖先的 task 返回 null（根级任务）。
   */
  function resolveSubName(node: Node<EditorNodeData> | undefined): string | null {
    if (!node) return null;
    if (node.type === 'editorSubPipeline') return (node.data?.label as string) || null;
    if (node.type === 'editorStartEnd' || node.type === 'editorPipeline') return null;
    let cur = node.parentId ? nodeMap.get(node.parentId) : undefined;
    while (cur) {
      if (cur.type === 'editorSubPipeline') return (cur.data?.label as string) || null;
      cur = cur.parentId ? nodeMap.get(cur.parentId) : undefined;
    }
    // 防御：兼容历史数据的 data.subpipelineName（拖拽新增节点该字段恒为空）
    return (node.data?.subpipelineName as string) || null;
  }

  // === Task 分组：按归属 sub，无归属的进入根级任务 ===
  const subMap = new Map<string, { subNode: Node<EditorNodeData>; taskNodes: Node<EditorNodeData>[] }>();
  for (const subNode of subPipelineNodes) {
    const name = subNode.data?.label as string;
    if (!name) continue;
    subMap.set(name, { subNode, taskNodes: [] });
  }

  const rootTaskNodes: Node<EditorNodeData>[] = [];
  for (const tn of taskNodes) {
    if (!tn.data?.task) continue;
    const sn = resolveSubName(tn);
    if (sn && subMap.has(sn)) {
      subMap.get(sn)!.taskNodes.push(tn);
    } else {
      rootTaskNodes.push(tn);
    }
  }

  // === 边语义解析 ===
  const taskDependsMap = new Map<string, Set<string>>(); // targetTaskId → dep task names
  const subDependsMap = new Map<string, Set<string>>(); // targetSubName → sourceSubName 集合
  const postParentSourceMap = new Map<string, string>(); // postParentId → 源容器 id
  const unmappableEdgeIds: string[] = [];

  const addTaskDep = (targetId: string, depName: string | undefined) => {
    if (!depName) return;
    if (!taskDependsMap.has(targetId)) taskDependsMap.set(targetId, new Set());
    taskDependsMap.get(targetId)!.add(depName);
  };
  const addSubDep = (targetSub: string, sourceSub: string) => {
    if (targetSub === sourceSub) return;
    if (!subDependsMap.has(targetSub)) subDependsMap.set(targetSub, new Set());
    subDependsMap.get(targetSub)!.add(sourceSub);
  };

  for (const edge of edges) {
    // 隐式边不序列化（由 execution_strategy 在运行时决定）
    if (edge.data?.edgeType === 'implicit') continue;

    const sourceNode = nodeMap.get(edge.source);
    const targetNode = nodeMap.get(edge.target);
    if (!sourceNode || !targetNode) continue; // 悬空边防御（反序列化层已过滤）

    // 1) Post 路由：容器 → Post 父容器
    if (targetNode.type === 'editorPostParent') {
      if (sourceNode.type === 'editorSubPipeline' || sourceNode.type === 'editorPipeline') {
        postParentSourceMap.set(targetNode.id, sourceNode.id);
      } else {
        unmappableEdgeIds.push(edge.id);
      }
      continue;
    }

    // 2) 哨兵固定拓扑（START→Pipeline→END 固定存在，无需序列化）
    if (sourceNode.type === 'editorStartEnd' || targetNode.type === 'editorStartEnd') {
      const isFixedTopology =
        (sourceNode.id === '__start__' && targetNode.id === '__pipeline__') ||
        (sourceNode.id === '__pipeline__' && targetNode.id === '__end__');
      if (!isFixedTopology) unmappableEdgeIds.push(edge.id);
      continue;
    }

    const sourceSub = resolveSubName(sourceNode);
    const targetSub = resolveSubName(targetNode);

    // 3) 两端都在容器内
    if (sourceSub && targetSub) {
      if (sourceSub === targetSub) {
        // 同容器：只有 task→task 有意义
        if (sourceNode.type === 'editorTask' && targetNode.type === 'editorTask') {
          addTaskDep(targetNode.id, sourceNode.data?.task?.name);
        } else {
          unmappableEdgeIds.push(edge.id);
        }
      } else {
        // 跨容器：统一映射为 sub 级依赖（后端依赖模型的粒度就是 sub）
        addSubDep(targetSub, sourceSub);
      }
      continue;
    }

    // 4) 两端都是根级 task
    if (!sourceSub && !targetSub) {
      if (sourceNode.type === 'editorTask' && targetNode.type === 'editorTask') {
        addTaskDep(targetNode.id, sourceNode.data?.task?.name);
        continue;
      }
    }

    // 5) 根级 task 与容器内节点混连、或其它无法表达的结构 → 显式报错
    unmappableEdgeIds.push(edge.id);
  }

  if (unmappableEdgeIds.length > 0) {
    errors.push(
      `存在无法保存的连线（请删除后重试）: ${unmappableEdgeIds.join(', ')}`,
    );
  }

  // === 收集 Post 数据 ===
  // postParentId → { hookType → TaskYAML[] }
  const postDataMap = new Map<string, Map<string, TaskYAML[]>>();

  for (const child of postChildNodes) {
    const parentId = child.parentId;
    if (!parentId) continue;

    const variant = child.data?.postVariant as string | undefined;
    const task = child.data?.task as TaskYAML | undefined;
    if (!variant || !task) continue;

    const key = postVariantToKey(variant);
    if (!key) continue;

    if (!postDataMap.has(parentId)) {
      postDataMap.set(parentId, new Map());
    }
    const hookMap = postDataMap.get(parentId)!;
    if (!hookMap.has(key)) {
      hookMap.set(key, []);
    }
    hookMap.get(key)!.push({ ...task });
  }

  // === 构建 SubPipeline 列表 ===
  const subpipelines: SubPipeline[] = [];

  const serializeTasks = (tns: Node<EditorNodeData>[]): TaskYAML[] => {
    // 按画布 y 坐标排序，保留用户看到的顺序
    const sorted = [...tns].sort((a, b) => a.position.y - b.position.y);
    return sorted.map((tn) => {
      const originalTask = tn.data?.task as TaskYAML;
      return {
        ...originalTask,
        depends_on: [...(taskDependsMap.get(tn.id) ?? [])],
        env: originalTask.env || {},
        retry: originalTask.retry ?? 0,
      } as TaskYAML;
    });
  };

  for (const [subName, { subNode, taskNodes: tns }] of subMap) {
    const tasks = serializeTasks(tns);

    const subDepends = subDependsMap.get(subName);
    const subPipeline: SubPipeline = {
      name: subName,
      depends_on: subDepends ? [...subDepends] : [],
      tasks,
    };

    // 填充 config
    if (subNode.data?.executionStrategy) {
      subPipeline.config = {
        env: {},
        retry: 0,
        on_failure: 'stop',
        execution_strategy: subNode.data.executionStrategy as string,
        ...(subNode.data?.maxConcurrentTasks != null ? { max_concurrent_tasks: subNode.data.maxConcurrentTasks as number } : {}),
      };
    }

    // 查找该 SubPipeline 的 Post 数据
    const subId = subNode.id;
    const postParentNode = postParentNodes.find(pn => {
      const sourceSubId = postParentSourceMap.get(pn.id);
      return sourceSubId === subId;
    });

    if (postParentNode && postDataMap.has(postParentNode.id)) {
      const hookMap = postDataMap.get(postParentNode.id)!;
      const postConfig: PostConfig = {};
      for (const [hookType, hookTasks] of hookMap) {
        if (hookType === 'on_fail') postConfig.on_fail = hookTasks;
        else if (hookType === 'on_success') postConfig.on_success = hookTasks;
        else if (hookType === 'always') postConfig.always = hookTasks;
      }
      if (Object.keys(postConfig).length > 0) {
        subPipeline.post = postConfig;
      }
    }

    subpipelines.push(subPipeline);
  }

  // === 根级 tasks → 隐式 SubPipeline ===
  // 与后端 _normalize 一致：以流水线名命名；若已存在同名 sub 则加后缀避免冲突。
  // 这样根级任务不会因为后端"pipelines 优先"的解析顺序而被忽略。
  if (rootTaskNodes.length > 0) {
    const implicitName = subMap.has(pipelineName) ? `${pipelineName}-root` : pipelineName;
    subpipelines.push({
      name: implicitName,
      depends_on: [],
      tasks: serializeTasks(rootTaskNodes),
    });
  }

  // === Pipeline 顶层 options ===
  const topOptions = pipelineNode?.data?.executionStrategy
    ? {
        env: {},
        retry: 0,
        on_failure: 'stop',
        execution_strategy: pipelineNode.data.executionStrategy as string,
        ...(pipelineNode.data?.maxConcurrentTasks != null
          ? { max_concurrent_tasks: pipelineNode.data.maxConcurrentTasks as number }
          : {}),
      }
    : undefined;

  // === 验证 ===
  // 检查空 SubPipeline（隐式 root sub 除外，其 tasks 必非空）
  for (const sub of subpipelines) {
    if (sub.tasks.length === 0) {
      errors.push(`SubPipeline "${sub.name}" 不能为空`);
    }
  }

  // 检查空 Task
  for (const tn of taskNodes) {
    if (!tn.data?.task?.name) {
      errors.push(`Task 节点 ${tn.id} 缺少名称`);
    }
  }

  const pipeline: PipelineDetail = {
    name: pipelineName,
    pipelines: subpipelines,
  };

  if (topOptions) {
    pipeline.options = topOptions as PipelineDetail['options'];
  }

  return { pipeline: errors.length > 0 ? null : pipeline, errors };
}
