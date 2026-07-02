import { load, dump, YAMLException } from 'js-yaml';
import type { PipelineDetail } from '@/types';

export interface YamlParseResult {
  success: boolean;
  pipeline?: PipelineDetail;
  error?: { message: string; line: number; column: number };
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
