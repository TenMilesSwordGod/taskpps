package components

import (
	"strings"
	"testing"

	"github.com/taskpps/ppsctl/models"
)

func TestNewRunDetailModel(t *testing.T) {
	m := NewRunDetailModel()
	if m.expanded == nil {
		t.Error("expanded map should not be nil")
	}
	if m.cursor != 0 {
		t.Errorf("cursor = %d, want 0", m.cursor)
	}
}

func TestRunDetailSetRun(t *testing.T) {
	m := NewRunDetailModel()
	started := "2024-01-01"
	finished := "2024-01-02"
	run := &models.Run{
		ID:           "abc123",
		PipelineName: "deploy",
		Status:       models.RunStatusRunning,
		StartedAt:    &started,
		FinishedAt:   &finished,
		Tasks: []models.TaskRun{
			{TaskName: "build", Status: models.TaskStatusSuccess, ExitCode: intPtr(0)},
			{TaskName: "test", Status: models.TaskStatusRunning},
			{TaskName: "deploy", Status: models.TaskStatusPending},
		},
	}
	m.SetRun(run)

	if m.run == nil {
		t.Error("run should not be nil")
	}
	if m.cursor != 0 {
		t.Errorf("cursor = %d, want 0", m.cursor)
	}
}

func TestRunDetailSetRunNil(t *testing.T) {
	m := NewRunDetailModel()
	m.SetRun(nil)
	if m.run != nil {
		t.Error("run should be nil")
	}
}

func TestRunDetailSetRunCursorAdjust(t *testing.T) {
	m := NewRunDetailModel()
	m.cursor = 10
	run := &models.Run{
		Tasks: []models.TaskRun{{TaskName: "t1"}, {TaskName: "t2"}},
	}
	m.SetRun(run)
	if m.cursor != 2 {
		t.Errorf("cursor = %d, want 2", m.cursor)
	}
}

func TestRunDetailSelectedRun(t *testing.T) {
	m := NewRunDetailModel()
	if m.SelectedRun() != nil {
		t.Error("expected nil for empty model")
	}

	run := &models.Run{ID: "test"}
	m.SetRun(run)
	sel := m.SelectedRun()
	if sel == nil || sel.ID != "test" {
		t.Error("expected run to be returned")
	}
}

func TestRunDetailSelectedTask(t *testing.T) {
	t.Run("nil_run", func(t *testing.T) {
		m := NewRunDetailModel()
		if m.SelectedTask() != nil {
			t.Error("expected nil for nil run")
		}
	})
}

func TestRunDetailView(t *testing.T) {
	t.Run("nil_run", func(t *testing.T) {
		m := NewRunDetailModel()
		view := m.View()
		if !strings.Contains(view, "select a run") {
			t.Errorf("view should show hint, got: %s", view)
		}
	})

	t.Run("with_run", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		exit0 := 0
		run := &models.Run{
			ID:           "abc123",
			PipelineName: "deploy",
			Status:       models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "build", Status: models.TaskStatusSuccess, ExitCode: &exit0, TaskType: "local"},
				{TaskName: "test", Status: models.TaskStatusRunning, TaskType: "local"},
				{TaskName: "deploy", Status: models.TaskStatusPending, TaskType: "ssh"},
			},
		}
		m.SetRun(run)
		view := m.View()
		if !strings.Contains(view, "abc123") {
			t.Errorf("view should contain run ID, got: %s", view)
		}
		if !strings.Contains(view, "deploy") {
			t.Errorf("view should contain pipeline name, got: %s", view)
		}
		if !strings.Contains(view, "build") {
			t.Errorf("view should contain task name, got: %s", view)
		}
	})

	t.Run("expanded_task", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		m.expanded[0] = true
		started := "2024-01-01"
		run := &models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "build", Status: models.TaskStatusSuccess, TaskType: "local", StartedAt: &started},
			},
		}
		m.SetRun(run)
		view := m.View()
		if !strings.Contains(view, "type:") {
			t.Errorf("expanded view should show task type, got: %s", view)
		}
		if !strings.Contains(view, "local") {
			t.Errorf("expanded view should show task type value, got: %s", view)
		}
	})

	t.Run("expanded_task_finished", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		m.expanded[0] = true
		started := "2024-01-01"
		finished := "2024-01-02"
		run := &models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "deploy", Status: models.TaskStatusSuccess, TaskType: "ssh", StartedAt: &started, FinishedAt: &finished},
			},
		}
		m.SetRun(run)
		view := m.View()
		if !strings.Contains(view, "start:") {
			t.Errorf("expanded view should show start, got: %s", view)
		}
		if !strings.Contains(view, "end:") {
			t.Errorf("expanded view should show end, got: %s", view)
		}
	})

	t.Run("empty_tasks", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		m.SetRun(&models.Run{ID: "abc", Status: models.RunStatusRunning})
		view := m.View()
		if !strings.Contains(view, "no tasks") {
			t.Errorf("view should show 'no tasks', got: %s", view)
		}
	})

	t.Run("finished_at", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		finished := "2024-01-02"
		run := &models.Run{
			ID:         "abc",
			Status:     models.RunStatusSuccess,
			FinishedAt: &finished,
		}
		m.SetRun(run)
		view := m.View()
		if !strings.Contains(view, "ran:") {
			t.Errorf("view should show ran, got: %s", view)
		}
	})

	t.Run("started_at", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		started := "2024-01-01"
		run := &models.Run{
			ID:        "abc",
			Status:    models.RunStatusRunning,
			StartedAt: &started,
		}
		m.SetRun(run)
		view := m.View()
		if !strings.Contains(view, "time:") {
			t.Errorf("view should show time, got: %s", view)
		}
	})

	t.Run("SetSize", func(t *testing.T) {
		m := NewRunDetailModel()
		m.SetSize(80, 24)
		if m.width != 79 || m.height != 24 {
			t.Errorf("size = (%d,%d), want (79,24)", m.width, m.height)
		}
	})
}

func intPtr(i int) *int { return &i }
