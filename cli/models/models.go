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
	ID         string     `json:"id"`
	RunID      string     `json:"run_id"`
	TaskName   string     `json:"task_name"`
	TaskType   string     `json:"task_type"`
	Status     TaskStatus `json:"status"`
	ExitCode   *int       `json:"exit_code"`
	LogPath    string     `json:"log_path"`
	StartedAt  *string    `json:"started_at"`
	FinishedAt *string    `json:"finished_at"`
	CreatedAt  string     `json:"created_at"`
}

type Run struct {
	ID           string    `json:"id"`
	PipelineName string    `json:"pipeline_name"`
	PipelineFile string    `json:"pipeline_file"`
	Status       RunStatus `json:"status"`
	Params       string    `json:"params"`
	StartedAt    *string   `json:"started_at"`
	FinishedAt   *string   `json:"finished_at"`
	CreatedAt    string    `json:"created_at"`
	Tasks        []TaskRun `json:"tasks"`
}

type RunListResponse struct {
	Items []Run `json:"items"`
	Total int   `json:"total"`
}

type CreateRunRequest struct {
	Pipeline string                 `json:"pipeline"`
	Params   map[string]interface{} `json:"params"`
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
