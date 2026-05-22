package models

import "testing"

func TestRunStatusConstants(t *testing.T) {
	testCases := []struct {
		name     string
		status   RunStatus
		expected string
	}{
		{"Pending", RunStatusPending, "pending"},
		{"Running", RunStatusRunning, "running"},
		{"Success", RunStatusSuccess, "success"},
		{"Failed", RunStatusFailed, "failed"},
		{"Cancelled", RunStatusCancelled, "cancelled"},
		{"Partial", RunStatusPartial, "partial"},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			if string(tc.status) != tc.expected {
				t.Errorf("RunStatus %s = %s, want %s", tc.name, tc.status, tc.expected)
			}
		})
	}
}

func TestTaskStatusConstants(t *testing.T) {
	testCases := []struct {
		name     string
		status   TaskStatus
		expected string
	}{
		{"Pending", TaskStatusPending, "pending"},
		{"Running", TaskStatusRunning, "running"},
		{"Success", TaskStatusSuccess, "success"},
		{"Failed", TaskStatusFailed, "failed"},
		{"Skipped", TaskStatusSkipped, "skipped"},
		{"Cancelled", TaskStatusCancelled, "cancelled"},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			if string(tc.status) != tc.expected {
				t.Errorf("TaskStatus %s = %s, want %s", tc.name, tc.status, tc.expected)
			}
		})
	}
}

func TestRunStruct(t *testing.T) {
	run := Run{
		ID:           "test-123",
		PipelineName: "test-pipeline",
		PipelineFile: "test.yaml",
		Status:       RunStatusSuccess,
	}

	if run.ID != "test-123" {
		t.Errorf("Run.ID = %s, want test-123", run.ID)
	}
	if run.PipelineName != "test-pipeline" {
		t.Errorf("Run.PipelineName = %s, want test-pipeline", run.PipelineName)
	}
	if run.Status != RunStatusSuccess {
		t.Errorf("Run.Status = %s, want success", run.Status)
	}
}

func TestTaskRunStruct(t *testing.T) {
	task := TaskRun{
		ID:       "task-456",
		RunID:    "test-123",
		TaskName: "build",
		Status:   TaskStatusSuccess,
	}

	if task.ID != "task-456" {
		t.Errorf("TaskRun.ID = %s, want task-456", task.ID)
	}
	if task.TaskName != "build" {
		t.Errorf("TaskRun.TaskName = %s, want build", task.TaskName)
	}
}
