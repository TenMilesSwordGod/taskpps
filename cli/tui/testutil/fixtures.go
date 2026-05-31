package testutil

import (
	"strings"

	"github.com/taskpps/ppsctl/models"
)

var TestTime1 = "2024-01-15T10:30:00Z"
var TestTime2 = "2024-01-15T11:45:00Z"
var TestExit0 = 0
var TestExit1 = 1

func MakeTestRuns() []models.Run {
	return []models.Run{
		{
			ID:           "run-abc12345",
			PipelineName: "deploy",
			Status:       models.RunStatusRunning,
			StartedAt:    &TestTime1,
			Tasks: []models.TaskRun{
				{TaskName: "build", SubpipelineName: "build", TaskType: "local", Status: models.TaskStatusSuccess, ExitCode: &TestExit0, StartedAt: &TestTime1, FinishedAt: &TestTime2},
				{TaskName: "test", SubpipelineName: "build", TaskType: "local", Status: models.TaskStatusRunning, StartedAt: &TestTime1},
				{TaskName: "deploy", SubpipelineName: "deploy", TaskType: "ssh", Status: models.TaskStatusPending},
			},
		},
		{
			ID:           "run-def67890",
			PipelineName: "build",
			Status:       models.RunStatusSuccess,
			StartedAt:    &TestTime1,
			FinishedAt:   &TestTime2,
			Tasks: []models.TaskRun{
				{TaskName: "compile", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusSuccess, ExitCode: &TestExit0, StartedAt: &TestTime1, FinishedAt: &TestTime2},
			},
		},
		{
			ID:           "run-ghi11111",
			PipelineName: "test-pipeline",
			Status:       models.RunStatusFailed,
			StartedAt:    &TestTime1,
			FinishedAt:   &TestTime2,
			Tasks: []models.TaskRun{
				{TaskName: "lint", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusSuccess, ExitCode: &TestExit0, StartedAt: &TestTime1, FinishedAt: &TestTime2},
				{TaskName: "unit-test", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusFailed, ExitCode: &TestExit1, StartedAt: &TestTime1, FinishedAt: &TestTime2},
			},
		},
	}
}

func MakeTestRunAllStatuses() models.Run {
	return models.Run{
		ID:           "run-all-status",
		PipelineName: "multi-status",
		Status:       models.RunStatusRunning,
		StartedAt:    &TestTime1,
		Tasks: []models.TaskRun{
			{TaskName: "pending-task", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusPending},
			{TaskName: "running-task", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusRunning, StartedAt: &TestTime1},
			{TaskName: "success-task", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusSuccess, ExitCode: &TestExit0, StartedAt: &TestTime1, FinishedAt: &TestTime2},
			{TaskName: "failed-task", SubpipelineName: "default", TaskType: "ssh", Status: models.TaskStatusFailed, ExitCode: &TestExit1, StartedAt: &TestTime1, FinishedAt: &TestTime2},
			{TaskName: "skipped-task", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusSkipped},
			{TaskName: "cancelled-task", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusCancelled},
		},
	}
}

func MakeLongIDRun() models.Run {
	return models.Run{
		ID:           strings.Repeat("a", 200),
		PipelineName: "long-id-pipeline",
		Status:       models.RunStatusRunning,
		StartedAt:    &TestTime1,
	}
}

func MakeLongPipelineNameRun() models.Run {
	return models.Run{
		ID:           "short-id",
		PipelineName: strings.Repeat("X", 200),
		Status:       models.RunStatusRunning,
		StartedAt:    &TestTime1,
	}
}

func MakeEmptyPipelineNameRun() models.Run {
	return models.Run{
		ID:           "run-empty-name",
		PipelineName: "",
		Status:       models.RunStatusPending,
	}
}

func MakeSingleCharIDRun() models.Run {
	return models.Run{
		ID:           "a",
		PipelineName: "tiny",
		Status:       models.RunStatusSuccess,
		StartedAt:    &TestTime1,
	}
}

func MakeMixedPipelineRuns() []models.Run {
	return []models.Run{
		{ID: "r1", PipelineName: "deploy-production", Status: models.RunStatusRunning, StartedAt: &TestTime1},
		{ID: "r2", PipelineName: "build-service", Status: models.RunStatusSuccess, StartedAt: &TestTime1, FinishedAt: &TestTime2},
		{ID: "r3", PipelineName: "test-integration", Status: models.RunStatusFailed, StartedAt: &TestTime1, FinishedAt: &TestTime2},
		{ID: "r4", PipelineName: "release-candidate", Status: models.RunStatusPending},
		{ID: "r5", PipelineName: "monitor-health", Status: models.RunStatusCancelled, StartedAt: &TestTime1, FinishedAt: &TestTime2},
	}
}

func MakeLongLogContent(lineCount int) string {
	var b strings.Builder
	for i := 0; i < lineCount; i++ {
		b.WriteString("log line ")
		b.WriteString(strings.Repeat("x", 50))
		b.WriteString("\n")
	}
	return b.String()
}

func MakeLongSingleLineLog(charCount int) string {
	return strings.Repeat("A", charCount)
}
