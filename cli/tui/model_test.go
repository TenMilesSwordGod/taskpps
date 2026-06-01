package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
)

func TestNewModel(t *testing.T) {
	m := makeTestModel()

	if m.state.FocusedPanel != FocusRunList {
		t.Errorf("focusedPanel = %v, want FocusRunList", m.state.FocusedPanel)
	}
	if m.client == nil {
		t.Error("client should not be nil")
	}
	if m.state.Quit {
		t.Error("quit should be false")
	}
}

func TestNewModelWithTargetRun(t *testing.T) {
	m := makeTestModel()
	m2 := NewModel(m.client, "abc123")
	if m2.targetRunID != "abc123" {
		t.Errorf("targetRunID = %s, want abc123", m2.targetRunID)
	}
}

func TestPanelFocus(t *testing.T) {
	t.Run("focusNext", func(t *testing.T) {
		m := Model{state: NewAppState()}
		m.state.FocusedPanel = FocusRunList
		if m.focusNext() != FocusRightPanel {
			t.Error("focusNext from RunList should go to RightPanel")
		}

		m.state.FocusedPanel = FocusRightPanel
		if m.focusNext() != FocusRunList {
			t.Error("focusNext from RightPanel should go to RunList")
		}
	})

	t.Run("focusPrev", func(t *testing.T) {
		m := Model{state: NewAppState()}
		m.state.FocusedPanel = FocusRunList
		if m.focusPrev() != FocusRightPanel {
			t.Error("focusPrev from RunList should go to RightPanel")
		}

		m.state.FocusedPanel = FocusRightPanel
		if m.focusPrev() != FocusRunList {
			t.Error("focusPrev from RightPanel should go to RunList")
		}
	})
}

func TestInit(t *testing.T) {
	m := makeTestModel()
	cmds := m.Init()
	if cmds == nil {
		t.Error("Init should return commands")
	}
}

func TestModelQuit(t *testing.T) {
	m := makeTestModel()
	if m.state.Quit {
		t.Error("quit should be false initially")
	}
	m.state.Quit = true
	if !m.state.Quit {
		t.Error("quit should be true after setting")
	}
}

func TestFetchFunctions(t *testing.T) {
	c := makeTestClient()

	t.Run("fetchRuns", func(t *testing.T) {
		cmd := fetchRuns(c)
		if cmd == nil {
			t.Error("fetchRuns should return a command")
		}
	})

	t.Run("fetchRun", func(t *testing.T) {
		cmd := fetchRun(c, "test123")
		if cmd == nil {
			t.Error("fetchRun should return a command")
		}
	})

	t.Run("fetchLogs", func(t *testing.T) {
		cmd := fetchLogs(c, "test123", "task1")
		if cmd == nil {
			t.Error("fetchLogs should return a command")
		}
	})
}

func TestStartWatch(t *testing.T) {
	t.Run("quit_with_q", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("q\n")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer())
		if err != nil {
			t.Logf("StartWatch error (expected from test client): %v", err)
		}
	})

	t.Run("quit_with_ctrl_c", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("\x03")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer())
		if err != nil {
			t.Logf("StartWatch ctrl+c error: %v", err)
		}
	})

	t.Run("quit_with_esc", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("\x1b")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer())
		if err != nil {
			t.Logf("StartWatch esc error: %v", err)
		}
	})

	t.Run("error_path", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("q\n")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer(), tea.WithAltScreen())
		if err != nil {
			t.Logf("StartWatch with both renderer options: %v", err)
		}
	})
}

func TestMergeRuns(t *testing.T) {
	t.Run("merge_preserves_tasks_from_existing", func(t *testing.T) {
		old := []models.Run{
			{ID: "r1", PipelineName: "p1", Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusSuccess},
				{TaskName: "t2", Status: models.TaskStatusRunning},
			}},
			{ID: "r2", PipelineName: "p2", Tasks: []models.TaskRun{
				{TaskName: "t3", Status: models.TaskStatusPending},
			}},
		}
		newRuns := []models.Run{
			{ID: "r1", PipelineName: "p1-updated", Tasks: nil},
			{ID: "r3", PipelineName: "p3", Tasks: nil},
		}

		merged := mergeRuns(old, newRuns)
		if len(merged) != 2 {
			t.Errorf("merged length = %d, want 2 (only newRuns are kept)", len(merged))
		}

		var r1 *models.Run
		for i := range merged {
			if merged[i].ID == "r1" {
				r1 = &merged[i]
				break
			}
		}
		if r1 == nil {
			t.Fatal("r1 not found in merged")
		}
		if r1.PipelineName != "p1-updated" {
			t.Errorf("r1.PipelineName = %q, want p1-updated", r1.PipelineName)
		}
		if len(r1.Tasks) != 2 {
			t.Errorf("r1 should preserve 2 tasks from existing, got %d", len(r1.Tasks))
		}
	})

	t.Run("merge_empty_old", func(t *testing.T) {
		newRuns := []models.Run{
			{ID: "r1", PipelineName: "p1"},
		}
		merged := mergeRuns(nil, newRuns)
		if len(merged) != 1 {
			t.Errorf("merged length = %d, want 1", len(merged))
		}
	})

	t.Run("merge_empty_new", func(t *testing.T) {
		old := []models.Run{
			{ID: "r1", PipelineName: "p1"},
		}
		merged := mergeRuns(old, nil)
		if len(merged) != 0 {
			t.Errorf("merged length = %d, want 0 (only newRuns are kept)", len(merged))
		}
	})

	t.Run("merge_both_empty", func(t *testing.T) {
		merged := mergeRuns(nil, nil)
		if len(merged) != 0 {
			t.Errorf("merged length = %d, want 0", len(merged))
		}
	})

	t.Run("merge_new_overrides_status", func(t *testing.T) {
		old := []models.Run{
			{ID: "r1", Status: models.RunStatusPending, Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusPending},
			}},
		}
		newRuns := []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
		}
		merged := mergeRuns(old, newRuns)
		if merged[0].Status != models.RunStatusRunning {
			t.Errorf("status = %v, want Running", merged[0].Status)
		}
		if len(merged[0].Tasks) != 1 {
			t.Error("tasks should be preserved from old when new has none")
		}
	})

	t.Run("merge_existing_tasks_preserved_even_when_new_has_tasks", func(t *testing.T) {
		old := []models.Run{
			{ID: "r1", Tasks: []models.TaskRun{
				{TaskName: "old", Status: models.TaskStatusSuccess},
			}},
		}
		newRuns := []models.Run{
			{ID: "r1", Tasks: []models.TaskRun{
				{TaskName: "new", Status: models.TaskStatusRunning},
			}},
		}
		merged := mergeRuns(old, newRuns)
		if len(merged[0].Tasks) != 1 || merged[0].Tasks[0].TaskName != "old" {
			t.Error("existing tasks should be preserved when they exist, even if new run has tasks")
		}
	})
}

func TestComputeRunsHash(t *testing.T) {
	runs1 := []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	runs2 := []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	runs3 := []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusSuccess},
	}

	h1 := computeRunsHash(runs1)
	h2 := computeRunsHash(runs2)
	h3 := computeRunsHash(runs3)

	if h1 != h2 {
		t.Error("same runs should produce same hash")
	}
	if h1 == h3 {
		t.Error("different runs should produce different hash")
	}
}

func TestAppState(t *testing.T) {
	s := NewAppState()
	if s.FocusedPanel != FocusRunList {
		t.Error("default focus should be RunList")
	}
	if s.Ready {
		t.Error("should not be ready initially")
	}
	if s.Quit {
		t.Error("should not quit initially")
	}
}
