import { load } from 'js-yaml';

/**
 * YAML 编辑器内的变量悬浮解析（v3 2026-09）。
 *
 * 设计决策（为什么这么写）：
 * - 悬浮只做"静态可确定"的解析：从当前 YAML 上下文取 env/params 定义值，
 *   agent/credential 由调用方注入项目配置。运行时才产生的值（task.output、
 *   PIPELINE_ID、artifact 等）不猜测、不硬编码，统一标注"运行时可用"。
 * - env 按光标所在 task/subpipeline 就近解析，与执行引擎"task 覆盖 pipeline"的
 *   生效顺序一致，避免多任务同名 env 时提示错值。位置判断用缩进扫描而非 AST，
 *   因为 js-yaml 不提供节点位置，扫描对典型缩进 YAML 已足够且易于单测。
 * - 解析失败（YAML 非法）不抛错，降级为"运行时注入"提示，编辑器仍可用。
 */

export interface AgentVariableSource {
  agent_id: string;
  host: string;
  port: number;
}

export interface CredentialVariableSource {
  id: string;
  name: string;
  type: string;
}

export interface VariableInfo {
  expression: string;
  /** 变量类型（中文，用于悬浮展示） */
  kind: string;
  /** 静态可解析出的值；运行时变量或无定义时为 undefined */
  value?: string;
  /** 值的来源作用域（如 task.compile.env） */
  source?: string;
  /** 无法给出 value 时的说明 */
  description?: string;
}

export interface VariableResolveOptions {
  /** 光标所在行（1-indexed），用于选择最近的 env 作用域 */
  lineNumber?: number;
  /** Agent 配置（key 支持 agent_id / 名称） */
  agents?: Map<string, AgentVariableSource>;
  /** 凭据元数据（key 支持 id / 名称；密码类字段后端不回传） */
  credentials?: Map<string, CredentialVariableSource>;
  /** 凭据列表不可用（非管理员），用于区分"未找到"与"无权查看" */
  credentialsUnavailable?: boolean;
}

interface EnvScope {
  source: string;
  env: Record<string, string>;
  taskName?: string;
  subName?: string;
}

export interface YamlVariableIndex {
  /** 已解析的 YAML 文档，供通用 dot-path 查询；解析失败为 null */
  doc: Record<string, unknown> | null;
  params: Map<string, { hasDefault: boolean; default?: unknown; label?: string }>;
  /** 所有 env 作用域，按生效优先级从低到高排列（后者覆盖前者） */
  envScopes: EnvScope[];
  /** task 名 → 该 task 的 env 作用域（同名 task 可能有多个） */
  taskEnvs: Map<string, EnvScope[]>;
  subEnvs: Map<string, EnvScope>;
  /** 原文行，用于光标定位作用域 */
  lines: string[];
}

/** 内置变量说明（运行时才有值，静态只解释含义） */
const BUILTIN_VARIABLES: Record<string, string> = {
  PIPELINE_ID: '当前 Pipeline 运行 ID（运行时可用）',
  JOB_ID: '当前 Job 运行 ID（运行时可用）',
  STEP_ID: '当前 Step 运行 ID（运行时可用）',
  WORKSPACE: '工作目录路径（运行时可用）',
};

export function findVariableAt(
  lineText: string,
  column: number,
): { expression: string; from: number; to: number } | null {
  const re = /\$\{[^}]+\}/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(lineText)) !== null) {
    const from = match.index;
    const to = from + match[0].length;
    if (column >= from && column < to) {
      return { expression: match[0], from, to };
    }
  }
  return null;
}

export function buildVariableIndex(yamlText: string): YamlVariableIndex {
  const lines = yamlText.split('\n');
  let doc: Record<string, unknown> | null = null;
  try {
    const parsed = load(yamlText);
    if (isRecord(parsed)) doc = parsed;
  } catch {
    // v3: 非法 YAML 不阻断编辑器，悬浮降级为运行时说明
    doc = null;
  }

  const envScopes: EnvScope[] = [];
  const taskEnvs = new Map<string, EnvScope[]>();
  const subEnvs = new Map<string, EnvScope>();
  const params = new Map<string, { hasDefault: boolean; default?: unknown; label?: string }>();

  const registerScope = (scope: EnvScope) => {
    envScopes.push(scope);
    if (scope.taskName) {
      const list = taskEnvs.get(scope.taskName) ?? [];
      list.push(scope);
      taskEnvs.set(scope.taskName, list);
    }
    if (scope.subName && !scope.taskName) {
      subEnvs.set(scope.subName, scope);
    }
  };

  if (doc) {
    const rootEnv = toEnv(doc.env);
    if (rootEnv) registerScope({ source: 'env', env: rootEnv });

    const options = asRecord(doc.options);
    const optionsEnv = options ? toEnv(options.env) : null;
    if (optionsEnv) registerScope({ source: 'options.env', env: optionsEnv });

    const config = asRecord(doc.config);
    const configEnv = config ? toEnv(config.env) : null;
    if (configEnv) registerScope({ source: 'config.env', env: configEnv });

    for (const subRaw of asArray(doc.pipelines)) {
      const sub = asRecord(subRaw);
      if (!sub) continue;
      const subName = toName(sub.name);
      if (!subName) continue;

      const subConfig = asRecord(sub.config);
      const subEnv = subConfig ? toEnv(subConfig.env) : null;
      if (subEnv && Object.keys(subEnv).length > 0) {
        registerScope({
          source: `subpipeline.${subName}.config.env`,
          env: subEnv,
          subName,
        });
      }

      for (const taskRaw of asArray(sub.tasks)) {
        const task = asRecord(taskRaw);
        const taskName = task ? toName(task.name) : null;
        const taskEnv = task ? toEnv(task.env) : null;
        if (task && taskName && taskEnv && Object.keys(taskEnv).length > 0) {
          registerScope({
            source: `task.${taskName}.env`,
            env: taskEnv,
            taskName,
            subName,
          });
        }
      }
    }

    for (const taskRaw of asArray(doc.tasks)) {
      const task = asRecord(taskRaw);
      const taskName = task ? toName(task.name) : null;
      const taskEnv = task ? toEnv(task.env) : null;
      if (task && taskName && taskEnv && Object.keys(taskEnv).length > 0) {
        registerScope({
          source: `task.${taskName}.env`,
          env: taskEnv,
          taskName,
        });
      }
    }

    collectParams(doc.params, params);
  }

  return { doc, params, envScopes, taskEnvs, subEnvs, lines };
}

export function resolveVariableInfo(
  expression: string,
  index: YamlVariableIndex,
  options: VariableResolveOptions = {},
): VariableInfo {
  const inner = expression.startsWith('${') && expression.endsWith('}')
    ? expression.slice(2, -1).trim()
    : expression;

  if (inner.startsWith('env.')) {
    return resolveEnv(expression, inner.slice(4), index, options);
  }
  if (inner.startsWith('params.')) {
    return resolveParam(expression, inner.slice(7), index);
  }
  if (inner.startsWith('agent:')) {
    return resolveAgent(expression, inner.slice(6), options);
  }
  if (inner.startsWith('credential:')) {
    return resolveCredential(expression, inner.slice(11), options);
  }
  if (inner.startsWith('task.') && inner.endsWith('.output')) {
    return {
      expression,
      kind: '上游任务输出',
      description: '上游任务输出，运行时产生，静态不可解析',
    };
  }
  if (inner.startsWith('artifact:')) {
    return {
      expression,
      kind: '制品引用',
      description: '运行时解析为本次运行的制品路径',
    };
  }
  if (inner in BUILTIN_VARIABLES) {
    return { expression, kind: '内置变量', description: BUILTIN_VARIABLES[inner] };
  }

  const value = lookupPath(index.doc, inner);
  if (value !== undefined) {
    return { expression, kind: '变量', value: formatValue(value), source: 'YAML' };
  }
  return { expression, kind: '变量', description: '运行时变量或未定义' };
}

function resolveEnv(
  expression: string,
  name: string,
  index: YamlVariableIndex,
  options: VariableResolveOptions,
): VariableInfo {
  const { task, sub } = options.lineNumber != null
    ? findEnclosingNames(index.lines, options.lineNumber)
    : { task: undefined, sub: undefined };

  // 1) 光标所在 task（同名 task 时优先与所在 subpipeline 匹配的作用域）
  if (task) {
    const scopes = index.taskEnvs.get(task) ?? [];
    const scope = scopes.find((s) => !sub || !s.subName || s.subName === sub)
      ?? scopes[0];
    if (scope && name in scope.env) {
      return { expression, kind: '环境变量', value: scope.env[name], source: scope.source };
    }
  }

  // 2) 光标所在 subpipeline 配置
  if (sub) {
    const scope = index.subEnvs.get(sub);
    if (scope && name in scope.env) {
      return { expression, kind: '环境变量', value: scope.env[name], source: scope.source };
    }
  }

  // 3) 全局作用域（config → options → 顶层 env，按生效优先级从高到低）
  for (let i = index.envScopes.length - 1; i >= 0; i--) {
    const scope = index.envScopes[i];
    if (scope.taskName || !(name in scope.env)) continue;
    return { expression, kind: '环境变量', value: scope.env[name], source: scope.source };
  }

  return {
    expression,
    kind: '环境变量',
    description: '未在 YAML 中定义，运行时由系统/运行环境注入',
  };
}

function resolveParam(
  expression: string,
  name: string,
  index: YamlVariableIndex,
): VariableInfo {
  const param = index.params.get(name);
  if (!param) {
    return { expression, kind: '参数', description: '未在 params 中声明，触发运行时由用户传入' };
  }
  if (!param.hasDefault) {
    return { expression, kind: '参数', description: '参数未声明默认值，触发运行时由用户传入' };
  }
  return {
    expression,
    kind: '参数',
    value: formatValue(param.default),
    source: `params.${name}.default`,
  };
}

function resolveAgent(
  expression: string,
  ref: string,
  options: VariableResolveOptions,
): VariableInfo {
  const dot = ref.lastIndexOf('.');
  const suffix = dot > 0 ? ref.slice(dot + 1) : '';
  const attr = suffix === 'host' || suffix === 'port' ? suffix : undefined;
  const name = attr ? ref.slice(0, dot) : ref;

  const agent = options.agents?.get(name);
  if (agent) {
    if (attr === 'port') {
      return { expression, kind: 'Agent 属性', value: String(agent.port), source: `agent:${name}` };
    }
    if (attr === 'host') {
      return { expression, kind: 'Agent 属性', value: agent.host, source: `agent:${name}` };
    }
    return {
      expression,
      kind: 'Agent 属性',
      value: agent.host ? `${agent.host}:${agent.port}` : undefined,
      source: `agent:${name}`,
    };
  }

  if (!options.agents) {
    return { expression, kind: 'Agent 属性', description: '未加载 Agent 配置（运行时解析）' };
  }
  return { expression, kind: 'Agent 属性', description: `未找到 Agent "${name}"` };
}

function resolveCredential(
  expression: string,
  name: string,
  options: VariableResolveOptions,
): VariableInfo {
  const credential = options.credentials?.get(name);
  if (credential) {
    return {
      expression,
      kind: '凭证',
      description: `凭据 "${credential.name}" 已配置，密码/口令不回传`,
    };
  }
  if (options.credentialsUnavailable) {
    return { expression, kind: '凭证', description: '凭据详情需管理员权限查看' };
  }
  if (options.credentials) {
    return { expression, kind: '凭证', description: `未找到凭据 "${name}"` };
  }
  return { expression, kind: '凭证', description: '凭据引用（运行时解析）' };
}

/** 从光标行向上按缩进扫描，推导所在 task / subpipeline 名称 */
function findEnclosingNames(
  lines: string[],
  lineNumber: number,
): { task?: string; sub?: string } {
  const start = Math.min(Math.max(lineNumber - 1, 0), lines.length - 1);
  let task: { indent: number; name: string } | null = null;
  let sub: { indent: number; name: string } | null = null;

  for (let i = start; i >= 0; i--) {
    const match = lines[i].match(/^(\s*)-\s+name:\s*["']?(.+?)["']?\s*(?:#.*)?$/);
    if (!match) continue;
    const entry = { indent: match[1].length, name: match[2].trim() };
    if (!task) {
      task = entry;
      continue;
    }
    if (entry.indent < task.indent) {
      sub = entry;
      break;
    }
  }
  return { task: task?.name, sub: sub?.name };
}

function collectParams(
  raw: unknown,
  target: Map<string, { hasDefault: boolean; default?: unknown; label?: string }>,
): void {
  // 兼容两种写法：列表（示例/推荐）与映射
  if (Array.isArray(raw)) {
    for (const item of raw) {
      const record = asRecord(item);
      const name = record ? toName(record.name) : null;
      if (!record || !name) continue;
      target.set(name, {
        hasDefault: record.default !== undefined && record.default !== null,
        default: record.default ?? undefined,
        label: typeof record.label === 'string' ? record.label : undefined,
      });
    }
    return;
  }
  const record = asRecord(raw);
  if (record) {
    for (const [name, value] of Object.entries(record)) {
      target.set(name, { hasDefault: value !== undefined && value !== null, default: value });
    }
  }
}

function lookupPath(doc: Record<string, unknown> | null, path: string): unknown {
  if (!doc) return undefined;
  let current: unknown = doc;
  for (const segment of path.split('.')) {
    const match = segment.match(/^([^[\]]*)((?:\[\d+\])*)$/);
    if (!match) return undefined;
    if (match[1]) {
      if (!isRecord(current)) return undefined;
      current = current[match[1]];
    }
    for (const idx of match[2].matchAll(/\[(\d+)\]/g)) {
      if (!Array.isArray(current)) return undefined;
      current = current[Number(idx[1])];
    }
    if (current === undefined) return undefined;
  }
  return current;
}

function toEnv(value: unknown): Record<string, string> | null {
  if (!isRecord(value)) return null;
  const env: Record<string, string> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (raw === null || raw === undefined) continue;
    env[key] = typeof raw === 'string' ? raw : formatValue(raw);
  }
  return env;
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return '';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function toName(value: unknown): string | null {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number') return String(value);
  return null;
}

/**
 * 构造变量悬浮提示的 DOM（CodeMirror tooltip 需要真实 DOM，不能用 React 节点）。
 * 放在 utils 而非编辑器组件文件：YamlEditor 只导出组件，满足 react-refresh 约束。
 */
export function buildVariableTooltipDom(info: VariableInfo): HTMLElement {
  const dom = document.createElement('div');
  dom.setAttribute('data-testid', 'yaml-variable-tooltip');
  dom.style.cssText =
    'font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;max-width:420px;' +
    'padding:6px 10px;background:#1f2430;color:#d7dae0;border:1px solid #3a4152;' +
    'border-radius:6px;box-shadow:0 4px 16px rgba(0,0,0,.4);';

  const expression = document.createElement('div');
  expression.textContent = info.expression;
  expression.style.cssText = 'font-weight:600;color:#c792ea;word-break:break-all;';
  dom.appendChild(expression);

  const meta = document.createElement('div');
  meta.textContent = info.source
    ? `类型：${info.kind} · 来源：${info.source}`
    : `类型：${info.kind}`;
  meta.style.cssText = 'color:#9aa4b2;';
  dom.appendChild(meta);

  if (info.value !== undefined) {
    const value = document.createElement('div');
    value.textContent = `值：${info.value}`;
    value.style.cssText = 'color:#7ee787;word-break:break-all;';
    dom.appendChild(value);
  } else if (info.description) {
    const description = document.createElement('div');
    description.textContent = info.description;
    description.style.cssText = 'color:#e5c07b;';
    dom.appendChild(description);
  }
  return dom;
}
