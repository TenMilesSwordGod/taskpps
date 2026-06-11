package models

type RunStatus string

const (
	RunStatusPending   RunStatus = "pending"
	RunStatusRunning   RunStatus = "running"
	RunStatusSuccess   RunStatus = "success"
	RunStatusFailed    RunStatus = "failed"
	RunStatusCancelled RunStatus = "cancelled"
	RunStatusPartial   RunStatus = "partial"
)

type TaskStatus string

const (
	TaskStatusPending   TaskStatus = "pending"
	TaskStatusRunning   TaskStatus = "running"
	TaskStatusSuccess   TaskStatus = "success"
	TaskStatusFailed    TaskStatus = "failed"
	TaskStatusSkipped   TaskStatus = "skipped"
	TaskStatusCancelled TaskStatus = "cancelled"
)

type TaskRun struct {
	ID              string     `json:"id"`
	RunID           string     `json:"run_id"`
	TaskName        string     `json:"task_name"`
	SubpipelineName string     `json:"subpipeline_name"`
	TaskType        string     `json:"task_type"`
	Status          TaskStatus `json:"status"`
	ExitCode        *int       `json:"exit_code"`
	LogPath         string     `json:"log_path"`
	StartedAt       *string    `json:"started_at"`
	FinishedAt      *string    `json:"finished_at"`
	CreatedAt       string     `json:"created_at"`
}

type Run struct {
	ID              string                 `json:"id"`
	PipelineName    string                 `json:"pipeline_name"`
	PipelineFile    string                 `json:"pipeline_file"`
	PipelineID      string                 `json:"pipeline_id"`
	PipelineVersion string                 `json:"pipeline_version"`
	ProjectID       *string                `json:"project_id"`
	Status          RunStatus              `json:"status"`
	Params          map[string]interface{} `json:"params"`
	ConsoleLogPath  string                 `json:"console_log_path"`
	StartedAt       *string                `json:"started_at"`
	FinishedAt      *string                `json:"finished_at"`
	CreatedAt       string                 `json:"created_at"`
	Tasks           []TaskRun              `json:"tasks"`
}

type RunListResponse struct {
	Items []Run `json:"items"`
	Total int   `json:"total"`
}

type CreateRunRequest struct {
	Pipeline  string                 `json:"pipeline"`
	Params    map[string]interface{} `json:"params"`
	ProjectID *string                `json:"project_id,omitempty"`
}

type CleanResponse struct {
	DeletedRuns int `json:"deleted_runs"`
	DeletedLogs int `json:"deleted_logs"`
}

type Trigger struct {
	ID           string `json:"id"`
	Type         string `json:"type"`
	Config       string `json:"config"`
	PipelineFile string `json:"pipeline_file"`
	Enabled      bool   `json:"enabled"`
	CreatedAt    string `json:"created_at"`
}

type CreateTriggerRequest struct {
	Type         string `json:"type"`
	Config       string `json:"config"`
	PipelineFile string `json:"pipeline_file"`
	Enabled      bool   `json:"enabled"`
}

type HealthResponse struct {
	Status  string `json:"status"`
	Version string `json:"version"`
}

type AgentCheckRequest struct {
	AgentID    string `json:"agent_id,omitempty"`
	FileFilter string `json:"file_filter,omitempty"`
	Timeout    int    `json:"timeout"`
}

type AgentCheckResult struct {
	AgentID    string `json:"agent_id"`
	Name       string `json:"name"`
	Type       string `json:"type"`
	Host       string `json:"host"`
	Port       int    `json:"port"`
	SourceFile string `json:"source_file"`
	Status     string `json:"status"`
	LatencyMs  int    `json:"latency_ms"`
	System     string `json:"system,omitempty"`
	Arch       string `json:"arch,omitempty"`
	Platform   string `json:"platform,omitempty"`
	Error      string `json:"error,omitempty"`
}

type AgentCheckSummary struct {
	Total     int `json:"total"`
	Connected int `json:"connected"`
	Failed    int `json:"failed"`
}

type AgentCheckResponse struct {
	Results []AgentCheckResult `json:"results"`
	Summary AgentCheckSummary  `json:"summary"`
}

type AgentStatus struct {
	AgentID         string  `json:"agent_id"`
	Connected       bool    `json:"connected"`
	Hostname        string  `json:"hostname"`
	Platform        string  `json:"platform"`
	AgentVersion    string  `json:"agent_version"`
	AgentPID        int     `json:"agent_pid"`
	ConnectedAt     float64 `json:"connected_at"`
	LastHeartbeat   float64 `json:"last_heartbeat"`
	RunningCommands int     `json:"running_commands"`
}

type AgentExecRequest struct {
	Command string            `json:"command"`
	Timeout int               `json:"timeout"`
	Cwd     string            `json:"cwd"`
	Env     map[string]string `json:"env,omitempty"`
}

type AgentExecResult struct {
	AgentID    string `json:"agent_id"`
	ExitCode   int    `json:"exit_code"`
	Stdout     string `json:"stdout"`
	Stderr     string `json:"stderr"`
	DurationMs int    `json:"duration_ms"`
	Error      string `json:"error,omitempty"`
}

type AgentDeployRequest struct {
	AgentID string `json:"agent_id"`
	Timeout int    `json:"timeout"`
}

type AgentDeployResult struct {
	Success  bool   `json:"success"`
	AgentID  string `json:"agent_id"`
	AgentPID int    `json:"agent_pid"`
	Error    string `json:"error,omitempty"`
}

type Project struct {
	ID           string  `json:"id"`
	Name         string  `json:"name"`
	Workdir      string  `json:"workdir"`
	RegisteredAt string  `json:"registered_at"`
	LastUsedAt   *string `json:"last_used_at"`
	Active       bool    `json:"active"`
}

type CreateProjectRequest struct {
	Workdir string `json:"workdir"`
	Name    string `json:"name,omitempty"`
}
