package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
)

func TestViewNotReady(t *testing.T) {
	m := makeTestModel()
	view := m.View()
	if !strings.Contains(view, "Initializing") {
		t.Errorf("view should show Initializing, got: %s", view)
	}
}

func TestViewQuitting(t *testing.T) {
	m := makeTestModel()
	m.state.Quit = true
	view := m.View()
	if view != "" {
		t.Errorf("view should be empty when quitting, got: %s", view)
	}
}

func TestViewReady(t *testing.T) {
	m := makeReadyModel()
	view := m.View()
	if view == "" {
		t.Error("view should not be empty when ready")
	}
	if !strings.Contains(view, "ppsctl watch") {
		t.Errorf("view should contain header, got: %s", view)
	}
}

func TestViewWithError(t *testing.T) {
	m := makeReadyModel()
	m.state.ErrorMsg = "Connection refused"
	view := m.View()
	if !strings.Contains(view, "ERR:") {
		t.Errorf("view should contain ERR, got: %s", view)
	}
}

func TestViewWithRuns(t *testing.T) {
	m := makeReadyModel()
	runs := []models.Run{
		{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "def67890", PipelineName: "build", Status: models.RunStatusSuccess},
	}
	m.state.Runs = runs
	m.runList.SetRuns(runs)

	view := m.View()
	if view == "" {
		t.Error("view should not be empty")
	}
}

func TestViewPanelFocus(t *testing.T) {
	m := makeReadyModel()
	runs := []models.Run{
		{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
	}
	m.state.Runs = runs
	m.runList.SetRuns(runs)

	t.Run("focus_runlist", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RunList focus")
		}
	})

	t.Run("focus_rundetail", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RightPanel focus")
		}
	})

	t.Run("focus_logviewer", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RightPanel focus")
		}
	})
}

func TestViewNarrowTerminal(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 80
	m.state.Height = 30
	m.resizeComponents()
	view := m.View()
	if view == "" {
		t.Error("view should render on narrow terminal")
	}
}

func TestViewWideTerminal(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 200
	m.state.Height = 50
	m.resizeComponents()
	view := m.View()
	if view == "" {
		t.Error("view should render on wide terminal")
	}
}

func TestViewEmptyRuns(t *testing.T) {
	m := makeReadyModel()
	m.state.Runs = nil
	m.runList.SetRuns(nil)
	view := m.View()
	if view == "" {
		t.Error("view should render with empty runs")
	}
}

func TestViewRenderFooter(t *testing.T) {
	m := makeReadyModel()
	m.state.Runs = []models.Run{{ID: "1", PipelineName: "test", Status: models.RunStatusRunning}}
	m.runList.SetRuns(m.state.Runs)

	footer := renderFooter(120, m.state, &m)
	if !strings.Contains(footer, "Runs:") {
		t.Errorf("footer should show Runs count, got: %s", footer)
	}
	if !strings.Contains(footer, "Tasks:") {
		t.Errorf("footer should show Tasks count, got: %s", footer)
	}
	if !strings.Contains(footer, "quit") {
		t.Errorf("footer should show key hints, got: %s", footer)
	}
}

func TestViewRenderFooterWithTasks(t *testing.T) {
	m := makeReadyModel()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "build", Status: models.TaskStatusSuccess},
				{TaskName: "test", Status: models.TaskStatusRunning},
				{TaskName: "deploy", Status: models.TaskStatusFailed},
			}},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&m.state.Runs[0])

	result := renderFooter(100, m.state, &m)
	if result == "" {
		t.Error("renderFooter should not return empty")
	}
	if !strings.Contains(result, "2/3") {
		t.Errorf("should show 2/3 tasks done, got: %s", result)
	}
}

func TestViewRenderFooterNarrow(t *testing.T) {
	m := makeReadyModel()
	footer := renderFooter(30, m.state, &m)
	if footer == "" {
		t.Error("footer should render on narrow width")
	}
}

func TestViewHeader(t *testing.T) {
	header := renderHeader(120)
	if !strings.Contains(header, "ppsctl watch") {
		t.Errorf("header should contain title, got: %s", header)
	}
	if !strings.Contains(header, "pipeline task monitor") {
		t.Errorf("header should contain subtitle, got: %s", header)
	}
}

func TestViewHeaderNarrow(t *testing.T) {
	header := renderHeader(40)
	if header == "" {
		t.Error("header should render on narrow width")
	}
}

func TestViewVerySmallSize(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 20
	m.state.Height = 5
	m.resizeComponents()
	view := m.View()
	if view == "" {
		t.Error("view should render even on very small terminal")
	}
}

func TestViewAllStatuses(t *testing.T) {
	m := makeReadyModel()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "pending", Status: models.RunStatusPending},
		{ID: "r2", PipelineName: "running", Status: models.RunStatusRunning},
		{ID: "r3", PipelineName: "success", Status: models.RunStatusSuccess},
		{ID: "r4", PipelineName: "failed", Status: models.RunStatusFailed},
		{ID: "r5", PipelineName: "cancelled", Status: models.RunStatusCancelled},
	}
	m.runList.SetRuns(m.state.Runs)
	view := m.View()
	if view == "" {
		t.Error("view should render all statuses")
	}
}

func TestViewResizePreservesState(t *testing.T) {
	m := makeReadyModelWithRuns([]models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
	})

	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail

	m2, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	model := m2.(Model)
	if model.state.FocusedPanel != FocusRightPanel {
		t.Error("resize should preserve focused panel")
	}
	if model.state.RightTab != TabDetail {
		t.Error("resize should preserve right tab")
	}
}

func TestRenderFooterEdgeCases(t *testing.T) {
	t.Run("zero_width", func(t *testing.T) {
		m := makeReadyModel()
		footer := renderFooter(0, m.state, &m)
		_ = footer
	})

	t.Run("very_wide", func(t *testing.T) {
		m := makeReadyModel()
		footer := renderFooter(500, m.state, &m)
		if footer == "" {
			t.Error("footer should render on very wide terminal")
		}
	})
}
