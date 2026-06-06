package models

import (
	"testing"
)

func TestRunStatus_Values(t *testing.T) {
	if RunStatusPending != "pending" {
		t.Errorf("expected pending, got %s", RunStatusPending)
	}
	if RunStatusRunning != "running" {
		t.Errorf("expected running, got %s", RunStatusRunning)
	}
	if RunStatusSuccess != "success" {
		t.Errorf("expected success, got %s", RunStatusSuccess)
	}
	if RunStatusFailed != "failed" {
		t.Errorf("expected failed, got %s", RunStatusFailed)
	}
	if RunStatusCancelled != "cancelled" {
		t.Errorf("expected cancelled, got %s", RunStatusCancelled)
	}
	if RunStatusPartial != "partial" {
		t.Errorf("expected partial, got %s", RunStatusPartial)
	}
}

func TestTaskStatus_Values(t *testing.T) {
	if TaskStatusPending != "pending" {
		t.Errorf("expected pending, got %s", TaskStatusPending)
	}
	if TaskStatusRunning != "running" {
		t.Errorf("expected running, got %s", TaskStatusRunning)
	}
	if TaskStatusSuccess != "success" {
		t.Errorf("expected success, got %s", TaskStatusSuccess)
	}
	if TaskStatusFailed != "failed" {
		t.Errorf("expected failed, got %s", TaskStatusFailed)
	}
	if TaskStatusSkipped != "skipped" {
		t.Errorf("expected skipped, got %s", TaskStatusSkipped)
	}
	if TaskStatusCancelled != "cancelled" {
		t.Errorf("expected cancelled, got %s", TaskStatusCancelled)
	}
}

func TestRun_Defaults(t *testing.T) {
	r := Run{}
	if r.ID != "" {
		t.Errorf("expected empty ID, got %s", r.ID)
	}
	if r.Status != "" {
		t.Errorf("expected empty status, got %s", r.Status)
	}
}

func TestTaskRun_Defaults(t *testing.T) {
	tr := TaskRun{}
	if tr.ID != "" {
		t.Errorf("expected empty ID, got %s", tr.ID)
	}
	if tr.Status != "" {
		t.Errorf("expected empty status, got %s", tr.Status)
	}
}

func TestCreateRunRequest_Defaults(t *testing.T) {
	req := CreateRunRequest{}
	if req.Pipeline != "" {
		t.Errorf("expected empty pipeline, got %s", req.Pipeline)
	}
}

func TestCleanResponse_Fields(t *testing.T) {
	r := CleanResponse{
		DeletedRuns: 5,
		DeletedLogs: 10,
	}
	if r.DeletedRuns != 5 {
		t.Errorf("expected 5, got %d", r.DeletedRuns)
	}
	if r.DeletedLogs != 10 {
		t.Errorf("expected 10, got %d", r.DeletedLogs)
	}
}

func TestTrigger_Defaults(t *testing.T) {
	tr := Trigger{}
	if tr.Enabled {
		t.Errorf("expected disabled by default")
	}
}

func TestHealthResponse_Fields(t *testing.T) {
	hr := HealthResponse{
		Status:  "ok",
		Version: "1.0.0",
	}
	if hr.Status != "ok" {
		t.Errorf("expected ok, got %s", hr.Status)
	}
	if hr.Version != "1.0.0" {
		t.Errorf("expected 1.0.0, got %s", hr.Version)
	}
}

func TestAgentCheckResult_Defaults(t *testing.T) {
	acr := AgentCheckResult{}
	if acr.Status != "" {
		t.Errorf("expected empty status, got %s", acr.Status)
	}
}

func TestAgentCheckSummary_Counts(t *testing.T) {
	summary := AgentCheckSummary{
		Total:     10,
		Connected: 8,
		Failed:    2,
	}
	if summary.Total != 10 {
		t.Errorf("expected 10, got %d", summary.Total)
	}
	if summary.Connected != 8 {
		t.Errorf("expected 8, got %d", summary.Connected)
	}
	if summary.Failed != 2 {
		t.Errorf("expected 2, got %d", summary.Failed)
	}
}

func TestAgentStatus_Fields(t *testing.T) {
	as := AgentStatus{
		AgentID:         "agent-1",
		Connected:       true,
		Hostname:        "test-host",
		Platform:        "linux",
		AgentVersion:    "1.0.0",
		AgentPID:        1234,
		RunningCommands: 5,
	}
	if as.AgentID != "agent-1" {
		t.Errorf("expected agent-1, got %s", as.AgentID)
	}
	if !as.Connected {
		t.Errorf("expected connected")
	}
	if as.Hostname != "test-host" {
		t.Errorf("expected test-host, got %s", as.Hostname)
	}
	if as.Platform != "linux" {
		t.Errorf("expected linux, got %s", as.Platform)
	}
	if as.AgentPID != 1234 {
		t.Errorf("expected 1234, got %d", as.AgentPID)
	}
	if as.RunningCommands != 5 {
		t.Errorf("expected 5, got %d", as.RunningCommands)
	}
}

func TestAgentExecRequest_Fields(t *testing.T) {
	req := AgentExecRequest{
		Command: "echo hello",
		Timeout: 30,
		Cwd:     "/tmp",
		Env:     map[string]string{"KEY": "VAL"},
	}
	if req.Command != "echo hello" {
		t.Errorf("expected echo hello, got %s", req.Command)
	}
	if req.Timeout != 30 {
		t.Errorf("expected 30, got %d", req.Timeout)
	}
	if req.Cwd != "/tmp" {
		t.Errorf("expected /tmp, got %s", req.Cwd)
	}
	if req.Env["KEY"] != "VAL" {
		t.Errorf("expected VAL, got %s", req.Env["KEY"])
	}
}

func TestAgentExecResult_Fields(t *testing.T) {
	result := AgentExecResult{
		AgentID:    "agent-1",
		ExitCode:   0,
		Stdout:     "hello",
		Stderr:     "",
		DurationMs: 150,
	}
	if result.AgentID != "agent-1" {
		t.Errorf("expected agent-1, got %s", result.AgentID)
	}
	if result.ExitCode != 0 {
		t.Errorf("expected 0, got %d", result.ExitCode)
	}
	if result.Stdout != "hello" {
		t.Errorf("expected hello, got %s", result.Stdout)
	}
	if result.DurationMs != 150 {
		t.Errorf("expected 150, got %d", result.DurationMs)
	}
}

func TestAgentDeployResult_Fields(t *testing.T) {
	result := AgentDeployResult{
		Success:  true,
		AgentID:  "agent-1",
		AgentPID: 5678,
	}
	if !result.Success {
		t.Errorf("expected success")
	}
	if result.AgentID != "agent-1" {
		t.Errorf("expected agent-1, got %s", result.AgentID)
	}
	if result.AgentPID != 5678 {
		t.Errorf("expected 5678, got %d", result.AgentPID)
	}
}

func TestRunListResponse_Fields(t *testing.T) {
	rlr := RunListResponse{
		Items: []Run{},
		Total: 0,
	}
	if rlr.Total != 0 {
		t.Errorf("expected 0, got %d", rlr.Total)
	}
	if len(rlr.Items) != 0 {
		t.Errorf("expected 0 items, got %d", len(rlr.Items))
	}
}