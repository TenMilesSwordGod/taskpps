import type { Node, Edge } from '@xyflow/react';
import type { PipelineDetail, TaskYAML, SubPipeline, PostConfig } from '@/types';
import type { EditorNodeData, EditorEdgeData } from './yamlToNodes';

/**
 * React Flow nodes + edges → PipelineDetail 序列化
 * 将可编辑画布上的节点和边转换回后端 YAML 数据模型
 *
 * 处理逻辑:
 *   1. 收集所有 SubPipeline → Task → depends_on 关系
 *   2. 收集 Post 父容器 → Post 子容器关系
 *   3. 收集 execution_strategy 属性
 *   4. 组装 PipelineDetail 对象
 *
 * 注意: 隐式边不参与序列化（它们由 execution_strategy 运行时决定）
 * 仅显式边写入 YAML 的 depends_on 字段
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

  // === 查找根 Pipeline 名称 ===
  const pipelineNode = nodes.find(n => n.id === '__pipeline__' || n.type === 'editorPipeline');
  const pipelineName = (pipelineNode?.data?.label as string) || 'unnamed';

  // === 收集所有 SubPipeline 节点 ===
  const subPipelineNodes = nodes.filter(n => n.type === 'editorSubPipeline');

  // === 收集所有 Task 节点 ===
  const taskNodes = nodes.filter(n => n.type === 'editorTask');

  // === 收集 Post 父容器节点 ===
  const postParentNodes = nodes.filter(n => n.type === 'editorPostParent');

  // === 收集 Post 子容器节点 ===
  const postChildNodes = nodes.filter(n => n.type === 'editorPostChild');

  // 构建 task node ID → node 映射
  const taskNodeMap = new Map<string, typeof taskNodes[0]>();
  for (const tn of taskNodes) {
    taskNodeMap.set(tn.id, tn);
  }

  // === 按 SubPipeline 分组 tasks ===
  const subMap = new Map<string, {
    subNode: typeof subPipelineNodes[0];
    taskNodes: typeof taskNodes[0][];
  }>();

  for (const subNode of subPipelineNodes) {
    if (!subNode.data?.label) continue;
    subMap.set(subNode.data.label as string, {
      subNode,
      taskNodes: [],
    });
  }

  for (const tn of taskNodes) {
    if (!tn.data?.subpipelineName || !tn.data?.task) continue;
    const sn = tn.data.subpipelineName as string;
    if (subMap.has(sn)) {
      subMap.get(sn)!.taskNodes.push(tn);
    }
  }

  // === 提取显式 depends_on ===
  const taskDependsMap = new Map<string, string[]>(); // taskId → [depTaskNames]

  for (const edge of edges) {
    if (edge.data?.edgeType !== 'explicit') continue;

    const sourceNode = taskNodeMap.get(edge.source);
    const targetNode = taskNodeMap.get(edge.target);

    // 仅处理同 SubPipeline 的 task→task 边
    if (sourceNode?.data?.subpipelineName === targetNode?.data?.subpipelineName &&
        sourceNode?.data?.task?.name && targetNode?.data?.task?.name) {
      const targetId = targetNode.id;
      if (!taskDependsMap.has(targetId)) {
        taskDependsMap.set(targetId, []);
      }
      taskDependsMap.get(targetId)!.push(sourceNode.data.task.name);
    }
  }

  // === 收集 Post 数据 ===
  // postParentId → { hookType → TaskYAML[] }
  const postDataMap = new Map<string, Map<string, TaskYAML[]>>();

  // key: parentTaskId (可为 subId 或 postParentId)
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

  // 找到 postParentNode → 源 SubPipeline 的映射
  const postParentSourceMap = new Map<string, string>(); // postParentId → subId
  for (const edge of edges) {
    if (edge.data?.edgeType === 'post_routing' && edge.target) {
      const sourceNode = nodes.find(n => n.id === edge.source);
      if (sourceNode?.type === 'editorSubPipeline') {
        postParentSourceMap.set(edge.target, edge.source);
      }
    }
  }

  // === 构建 SubPipeline 列表 ===
  const subpipelines: SubPipeline[] = [];

  for (const [subName, { subNode, taskNodes: tns }] of subMap) {
    const tasks: TaskYAML[] = [];

    // 按 y 坐标排序 task 节点
    const sorted = [...tns].sort((a, b) => a.position.y - b.position.y);

    for (const tn of sorted) {
      const originalTask = tn.data?.task as TaskYAML;
      if (!originalTask) continue;

      const dependsOn = taskDependsMap.get(tn.id) || [];

      const taskEntry: TaskYAML = {
        ...originalTask,
        depends_on: dependsOn,
        env: originalTask.env || {},
        retry: originalTask.retry ?? 0,
      };

      tasks.push(taskEntry);
    }

    const subPipeline: SubPipeline = {
      name: subName,
      depends_on: [], // 由跨容器边填充
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

  // === 计算 SubPipeline depends_on ===
  for (const edge of edges) {
    if (edge.data?.edgeType !== 'cross_container') continue;

    const sourceNode = nodes.find(n => n.id === edge.source);
    const targetNode = nodes.find(n => n.id === edge.target);

    if (sourceNode?.type === 'editorSubPipeline' && targetNode?.type === 'editorSubPipeline') {
      const sourceName = sourceNode.data?.label as string;
      const targetSub = subpipelines.find(s => s.name === targetNode.data?.label);
      if (sourceName && targetSub && !targetSub.depends_on.includes(sourceName)) {
        targetSub.depends_on.push(sourceName);
      }
    }
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
  // 检查空 SubPipeline
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

  // No SubPipelines but has tasks at root
  if (subpipelines.length === 0 && taskNodes.length > 0) {
    // 顶层 tasks 不被编辑器支持（编辑器中所有 task 必须在 SubPipeline 内）
    errors.push('所有 Task 必须位于 SubPipeline 容器内');
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
