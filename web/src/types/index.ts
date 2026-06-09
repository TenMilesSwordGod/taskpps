/** 运行状态 */
export type RunStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'partial';

/** 任务状态 */
export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'cancelled';

/** 任务类型 */
export type TaskType = 'command' | 'invoke' | 'steps' | 'git' | 'nexus' | 'ssh';

/** 运行响应 */
export interface RunResponse {
  id: string;
  pipeline_name: string;
  pipeline_file: string;
  pipeline_id: string;
  pipeline_version: string;
  version_changed: boolean;
  status: RunStatus;
  params: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  tasks: TaskRunResponse[];
}

/** 任务运行响应 */
export interface TaskRunResponse {
  id: string;
  run_id: string;
  task_name: string;
  subpipeline_name: string;
  task_type: TaskType;
  status: TaskStatus;
  exit_code: number | null;
  log_path: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

/** 运行列表响应 */
export interface RunListResponse {
  items: RunResponse[];
  total: number;
}

/** 流水线摘要 */
export interface PipelineSummary {
  name: string;
  file: string;
  task_count: number;
  subpipeline_count: number;
  last_run: {
    id: string;
    status: string;
    created_at: string | null;
  } | null;
  success_rate: number;
}

/** 流水线列表响应 */
export interface PipelineListResponse {
  items: PipelineSummary[];
}

/** Invoke 规格 */
export interface InvokeSpec {
  task: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
}

/** 任务步骤 */
export interface TaskStep {
  run: string;
  cd?: string | null;
  env: Record<string, string>;
}

/** Git 规格 */
export interface GitSpec {
  repo: string;
  ref?: string | null;
  credential?: string | null;
  dest: string;
  depth: number;
  submodules: boolean;
}

/** Nexus 规格 */
export interface NexusSpec {
  action: string;
  url: string;
  repository: string;
  credential?: string | null;
  group_id?: string | null;
  artifact_id?: string | null;
  version?: string | null;
  packaging: string;
  classifier?: string | null;
  files?: string[] | null;
  dest?: string | null;
  query?: string | null;
  source_repo?: string | null;
  target_repo?: string | null;
}

/** 流水线配置 */
export interface PipelineConfig {
  host?: string | null;
  credential?: string | null;
  env: Record<string, string>;
  timeout?: number | null;
  retry: number;
  on_failure: string;
  execution_strategy: string;
  max_parallel?: number | null;
  cwd?: string | null;
}

/** 任务 YAML 定义 */
export interface TaskYAML {
  name: string;
  command?: string | null;
  commands?: string[] | null;
  invoke?: InvokeSpec | null;
  steps?: TaskStep[] | null;
  git?: GitSpec | null;
  nexus?: NexusSpec | null;
  cwd?: string | null;
  host?: string | null;
  credential?: string | null;
  env: Record<string, string>;
  timeout?: number | null;
  retry: number;
  on_failure?: string | null;
  depends_on: string[];
  when?: string | null;
}

/** 子流水线 */
export interface SubPipeline {
  name: string;
  config?: PipelineConfig | null;
  depends_on: string[];
  tasks: TaskYAML[];
}

/** 流水线详情 */
export interface PipelineDetail {
  name: string;
  options?: PipelineConfig | null;
  config?: PipelineConfig | null;
  tasks?: TaskYAML[] | null;
  pipelines?: SubPipeline[] | null;
}

/** 健康检查响应 */
export interface HealthResponse {
  status: string;
  version: string;
  host: string;
  port: number;
}

/** Agent（Server）状态响应（仅已连接的） */
export interface AgentStatus {
  agent_id: string;
  connected: boolean;
  hostname: string;
  platform: string;
  system: string;
  arch: string;
  ip: string;
  agent_version: string;
  agent_pid: number;
  connected_at: number;
  last_heartbeat: number;
  running_commands: number;
}

/** Agent yaml 配置 + 实时状态（用于"所有服务器"列表） */
export interface AgentWithConfig {
  agent_id: string;
  name: string;
  type: string;
  host: string;
  port: number;
  source_file: string;
  connected: boolean;
  hostname: string;
  platform: string;
  system: string;
  arch: string;
  ip: string;
  agent_version: string;
  agent_pid: number;
  connected_at: number;
  last_heartbeat: number;
  running_commands: number;
  /** 网络可达性：unknown / reachable / unreachable */
  net_status: 'unknown' | 'reachable' | 'unreachable';
}

/** Agent check 探测单项结果 */
export interface AgentCheckResult {
  agent_id: string;
  name: string;
  type: string;
  host: string;
  port: number;
  source_file: string;
  status: string;
  latency_ms: number;
  system: string;
  arch: string;
  platform: string;
  error?: string;
}

/** Agent check 探测汇总 */
export interface AgentCheckSummary {
  total: number;
  connected: number;
  failed: number;
}

/** Agent check 探测响应 */
export interface AgentCheckResponse {
  results: AgentCheckResult[];
  summary: AgentCheckSummary;
}
