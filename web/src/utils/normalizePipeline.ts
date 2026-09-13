import type { PipelineDetail } from '@/types';

/**
 * 顶层 tasks 规范化（与后端 schema PipelineYAML._normalize 对齐）
 *
 * 为什么需要：统一渲染后的画布基于 SubPipeline 模型，仅声明顶层 tasks 的
 * pipeline 在画布上不可见（会被误判为数据丢失）；而保存后后端又会自动把
 * 顶层 tasks 包装为以流水线名命名的 SubPipeline，造成"预览 ≠ 保存后视图"。
 *
 * 触发条件与后端严格一致：tasks 非空 且 pipelines 为空/缺失。
 * 已经是 pipelines 结构时原样返回（幂等）。
 */
export function normalizeTopLevelTasks(pipeline: PipelineDetail): PipelineDetail {
  const tasks = pipeline.tasks;
  const pipelines = pipeline.pipelines;
  if (!tasks || tasks.length === 0) return pipeline;
  if (pipelines && pipelines.length > 0) return pipeline;

  return {
    ...pipeline,
    pipelines: [
      {
        name: pipeline.name,
        depends_on: [],
        tasks,
        config: pipeline.config ?? pipeline.options ?? null,
      },
    ],
    tasks: null,
  };
}
