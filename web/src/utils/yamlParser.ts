import { load, dump, YAMLException } from 'js-yaml';
import type { PipelineDetail, ValidationError } from '@/types';

export interface YamlParseResult {
  success: boolean;
  pipeline?: PipelineDetail;
  error?: ValidationError;
}

/**
 * 对齐后端 pydantic 模型的校验规则，将结构非法也识别为 validate error
 * 返回 null 表示通过，返回 ValidationError 表示非法
 */
function validatePipelineStructure(doc: Record<string, unknown>): ValidationError | null {
  // name 必填
  const name = doc.name;
  if (typeof name !== 'string' || !name.trim()) {
    return { message: '缺少必填字段 name', path: 'name' };
  }

  // tasks 若存在则必须为数组
  if (doc.tasks !== undefined && doc.tasks !== null && !Array.isArray(doc.tasks)) {
    return { message: 'tasks 应为数组', path: 'tasks' };
  }

  // pipelines 若存在则必须为数组
  if (doc.pipelines !== undefined && doc.pipelines !== null && !Array.isArray(doc.pipelines)) {
    return { message: 'pipelines 应为数组', path: 'pipelines' };
  }

  // options 若存在则必须为对象
  if (doc.options !== undefined && doc.options !== null && (typeof doc.options !== 'object' || Array.isArray(doc.options))) {
    return { message: 'options 应为对象', path: 'options' };
  }

  // config 若存在则必须为对象
  if (doc.config !== undefined && doc.config !== null && (typeof doc.config !== 'object' || Array.isArray(doc.config))) {
    return { message: 'config 应为对象', path: 'config' };
  }

  // 校验 subpipelines 结构
  if (Array.isArray(doc.pipelines)) {
    for (let i = 0; i < (doc.pipelines as unknown[]).length; i++) {
      const sub = (doc.pipelines as unknown[])[i] as Record<string, unknown> | null;
      if (!sub || typeof sub !== 'object') {
        return { message: `pipelines[${i}] 应为对象`, path: `pipelines[${i}]` };
      }
      if (typeof sub.name !== 'string' || !sub.name.trim()) {
        return { message: `pipelines[${i}] 缺少必填字段 name`, path: `pipelines[${i}].name` };
      }
      if (!Array.isArray(sub.tasks)) {
        return { message: `pipelines[${i}].tasks 应为数组`, path: `pipelines[${i}].tasks` };
      }
      // depends_on 若存在则必须为数组
      if (sub.depends_on !== undefined && sub.depends_on !== null && !Array.isArray(sub.depends_on)) {
        return { message: `pipelines[${i}].depends_on 应为数组`, path: `pipelines[${i}].depends_on` };
      }
      // 校验每个 task
      for (let j = 0; j < (sub.tasks as unknown[]).length; j++) {
        const task = (sub.tasks as unknown[])[j] as Record<string, unknown> | null;
        const taskErr = validateTaskStructure(task, `pipelines[${i}].tasks[${j}]`);
        if (taskErr) return taskErr;
      }
    }
  }

  // 校验顶层 tasks 结构
  if (Array.isArray(doc.tasks)) {
    for (let i = 0; i < (doc.tasks as unknown[]).length; i++) {
      const task = (doc.tasks as unknown[])[i] as Record<string, unknown> | null;
      const taskErr = validateTaskStructure(task, `tasks[${i}]`);
      if (taskErr) return taskErr;
    }
  }

  return null;
}

/** 校验单个 task 的结构 */
function validateTaskStructure(task: Record<string, unknown> | null, path: string): ValidationError | null {
  if (!task || typeof task !== 'object') {
    return { message: `${path} 应为对象`, path };
  }
  if (typeof task.name !== 'string' || !task.name.trim()) {
    return { message: `${path} 缺少必填字段 name`, path: `${path}.name` };
  }
  if (task.depends_on !== undefined && task.depends_on !== null && !Array.isArray(task.depends_on)) {
    return { message: `${path}.depends_on 应为数组`, path: `${path}.depends_on` };
  }
  if (task.retry !== undefined && task.retry !== null && typeof task.retry !== 'number') {
    return { message: `${path}.retry 应为数字`, path: `${path}.retry` };
  }
  if (task.env !== undefined && task.env !== null && (typeof task.env !== 'object' || Array.isArray(task.env))) {
    return { message: `${path}.env 应为对象`, path: `${path}.env` };
  }
  if (task.artifacts !== undefined && task.artifacts !== null && !Array.isArray(task.artifacts)) {
    return { message: `${path}.artifacts 应为数组`, path: `${path}.artifacts` };
  }
  if (task.post !== undefined && task.post !== null && (typeof task.post !== 'object' || Array.isArray(task.post))) {
    return { message: `${path}.post 应为对象`, path: `${path}.post` };
  }
  return null;
}

/** 将 YAML 文本解析为 PipelineDetail 对象 */
export function parseYamlToPipeline(yamlText: string): YamlParseResult {
  if (!yamlText.trim()) {
    return { success: false, error: { message: 'YAML 内容为空', line: 1, column: 1 } };
  }

  try {
    const doc = load(yamlText);

    if (!doc || typeof doc !== 'object') {
      return { success: false, error: { message: 'YAML 内容不是有效的对象', line: 1, column: 1 } };
    }

    const obj = doc as Record<string, unknown>;

    // v1 (2026-07): issue #195 — 增强结构校验，对齐后端 pydantic 模型
    const structErr = validatePipelineStructure(obj);
    if (structErr) {
      return { success: false, error: structErr };
    }

    const pipeline: PipelineDetail = {
      name: String(obj.name || 'unnamed'),
    };

    if (obj.options && typeof obj.options === 'object') {
      pipeline.options = obj.options as PipelineDetail['options'];
    }
    if (obj.config && typeof obj.config === 'object') {
      pipeline.config = obj.config as PipelineDetail['config'];
    }
    if (Array.isArray(obj.tasks)) {
      pipeline.tasks = obj.tasks as PipelineDetail['tasks'];
    }
    if (Array.isArray(obj.pipelines)) {
      pipeline.pipelines = obj.pipelines as PipelineDetail['pipelines'];
    }

    return { success: true, pipeline };
  } catch (err) {
    if (err instanceof YAMLException) {
      return {
        success: false,
        error: {
          message: err.message,
          line: err.mark?.line != null ? err.mark.line + 1 : 1,
          column: err.mark?.column != null ? err.mark.column + 1 : 1,
        },
      };
    }
    return {
      success: false,
      error: { message: err instanceof Error ? err.message : '未知解析错误', line: 1, column: 1 },
    };
  }
}

/** 递归移除 null/undefined/空对象/空数组，保留 0/false 等有意义 falsy 值 */
function stripDefaults(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    const cleaned = obj.map(stripDefaults).filter((v) => v !== null && v !== undefined);
    return cleaned.length > 0 ? cleaned : undefined;
  }
  if (obj !== null && typeof obj === 'object') {
    const cleaned: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const c = stripDefaults(v);
      if (c !== null && c !== undefined) {
        cleaned[k] = c;
      }
    }
    return Object.keys(cleaned).length > 0 ? cleaned : undefined;
  }
  return obj;
}

/** 将 PipelineDetail 对象序列化为 YAML 文本 */
export function pipelineToYaml(pipeline: PipelineDetail): string {
  const obj: Record<string, unknown> = { name: pipeline.name };
  if (pipeline.options) obj.options = pipeline.options;
  if (pipeline.config) obj.config = pipeline.config;
  // pipelines 存在时只输出 pipelines（tasks 已被归入 pipelines），避免重复
  if (pipeline.pipelines?.length) {
    obj.pipelines = pipeline.pipelines;
  } else if (pipeline.tasks?.length) {
    obj.tasks = pipeline.tasks;
  }
  return dump(stripDefaults(obj) as object, { indent: 2, lineWidth: 120, noRefs: true });
}
