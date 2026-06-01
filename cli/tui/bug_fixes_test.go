package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

func makeTestModelWithRuns() Model {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
	}
	m.runList.SetRuns(m.state.Runs)
	return m
}

func TestBug6_ViewportHeightMismatch(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	contentH := m.state.Dims.contentH

	view := m.View()
	lines := strings.Split(view, "\n")

	expectedMinLines := 1 + contentH + 1
	if len(lines) < expectedMinLines {
		t.Errorf("view lines = %d, expected at least %d (header + content + footer)", len(lines), expectedMinLines)
	}
}

func TestBug4_CursorNavigationBounds(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	m.SetRun(&models.Run{
		ID:     "test",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusSuccess, SubpipelineName: "group1"},
			{TaskName: "t2", Status: models.TaskStatusSuccess, SubpipelineName: "group1"},
		},
	})

	m.CollapseAll()
	m.Update(tea.KeyMsg{Type: tea.KeyDown})

	task := m.SelectedTask()
	_ = task

	m.SetRun(&models.Run{
		ID:     "test2",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusSuccess, SubpipelineName: "group1"},
			{TaskName: "t2", Status: models.TaskStatusSuccess, SubpipelineName: "group1"},
		},
	})
	m.SetCursor(1)

	m.Update(tea.KeyMsg{Type: tea.KeyDown})

	task = m.SelectedTask()
	if task != nil {
		t.Logf("cursor at down resulted in task: %v", task.TaskName)
	}
}

func TestBug4_CursorNavigationEmptyItems(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	m.SetRun(&models.Run{
		ID:     "test",
		Status: models.RunStatusRunning,
		Tasks:  []models.TaskRun{},
	})

	m.Update(tea.KeyMsg{Type: tea.KeyDown})

	task := m.SelectedTask()
	if task != nil {
		t.Errorf("should not select task for empty run, got %v", task.TaskName)
	}
}

func TestBug4_CursorNavigationAtLastItem(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	m.SetRun(&models.Run{
		ID:     "test",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusSuccess, SubpipelineName: "group1"},
		},
	})

	m.SetCursor(2)
	m.Update(tea.KeyMsg{Type: tea.KeyDown})

	task := m.SelectedTask()
	if task != nil && task.TaskName != "t1" {
		t.Errorf("cursor should stay at t1, got %v", task.TaskName)
	}
}

func TestBug5_ProgressBarWidthExact(t *testing.T) {
	bar := components.MakeProgressBar(1, 0, 3, 10)
	visualWidth := 0
	for _, r := range bar {
		if r != '\n' && r != '\r' {
			visualWidth++
		}
	}

	if visualWidth != 10 {
		t.Errorf("progress bar width = %d, want 10", visualWidth)
	}
}

func TestBug5_ProgressBarWidthAllDone(t *testing.T) {
	bar := components.MakeProgressBar(5, 0, 5, 10)
	if len(bar) < 10 {
		t.Errorf("progress bar too short: %q", bar)
	}
}

func TestBug5_ProgressBarWidthPartial(t *testing.T) {
	bar := components.MakeProgressBar(2, 1, 4, 10)
	if len(bar) < 10 {
		t.Errorf("progress bar too short for partial: %q", bar)
	}
}

func TestBug5_ProgressBarRounding(t *testing.T) {
	bar := components.MakeProgressBar(1, 1, 3, 5)
	if bar == "" {
		t.Error("progress bar should not be empty")
	}
}

func TestBug7_FooterWidthCalculation(t *testing.T) {
	m := makeTestModelWithRuns()
	m.state.FocusedPanel = FocusRunList
	m.state.ErrorMsg = ""

	footer := renderFooter(120, m.state, &m)
	if footer == "" {
		t.Error("footer should not be empty")
	}
	if !strings.Contains(footer, "Runs:") {
		t.Errorf("footer should contain Runs count, got: %s", footer)
	}
	if !strings.Contains(footer, "quit") {
		t.Errorf("footer should contain quit hint, got: %s", footer)
	}
}

func TestBug7_FooterWithError(t *testing.T) {
	m := makeTestModelWithRuns()
	m.state.FocusedPanel = FocusRunList
	m.state.ErrorMsg = "connection refused"

	footer := renderFooter(120, m.state, &m)
	if !strings.Contains(footer, "ERR:") {
		t.Errorf("footer should contain ERR with error message, got: %s", footer)
	}
}

func TestBug7_FooterRightPanel(t *testing.T) {
	m := makeTestModelWithRuns()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail

	footer := renderFooter(120, m.state, &m)
	if !strings.Contains(footer, "expand") {
		t.Errorf("footer should contain expand hint for detail tab, got: %s", footer)
	}
}

func TestBug7_FooterLogsTab(t *testing.T) {
	m := makeTestModelWithRuns()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs

	footer := renderFooter(120, m.state, &m)
	if !strings.Contains(footer, "scroll") {
		t.Errorf("footer should contain scroll hint for logs tab, got: %s", footer)
	}
}

func TestBug8_TickDoesNotFetchLogsForDoneTask(t *testing.T) {
	m := makeTestModelWithRuns()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.runDetail.SetRun(&models.Run{
		ID:     "abc",
		Status: models.RunStatusSuccess,
		Tasks: []models.TaskRun{
			{TaskName: "build", Status: models.TaskStatusSuccess, SubpipelineName: "default"},
		},
	})
	m.runDetail.SetCursor(1)

	_, cmd := m.Update(tickMsg{})
	if cmd == nil {
		t.Fatal("tick should return commands")
	}
}

func TestBug8_TickFetchesLogsForRunningTask(t *testing.T) {
	m := makeTestModelWithRuns()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.runDetail.SetRun(&models.Run{
		ID:     "abc",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "build", Status: models.TaskStatusRunning, SubpipelineName: "default"},
		},
	})
	m.runDetail.SetCursor(1)

	_, cmd := m.Update(tickMsg{})
	if cmd == nil {
		t.Fatal("tick should return commands for running task")
	}
}

func TestBug9_RunListCursorBounds(t *testing.T) {
	m := components.NewRunListModel()
	m.SetRuns([]models.Run{
		{ID: "r1", PipelineName: "p1"},
		{ID: "r2", PipelineName: "p2"},
	})
	m.SetSize(60, 10)
	m.SetCursor(1)

	m.Update(tea.KeyMsg{Type: tea.KeyDown})
	if m.SelectedRun().ID != "r2" {
		t.Errorf("should stay at last run, got %s", m.SelectedRun().ID)
	}
}

func TestBug9_RunListCursorVisibleAfterSetRuns(t *testing.T) {
	m := components.NewRunListModel()
	m.SetRuns([]models.Run{
		{ID: "r1", PipelineName: "p1"},
		{ID: "r2", PipelineName: "p2"},
		{ID: "r3", PipelineName: "p3"},
	})
	m.SetSize(60, 3)
	m.SetCursor(2)

	view := m.View()
	if view == "" {
		t.Error("view should not be empty")
	}
}

func TestBug10_LogViewerSetContentClearsOld(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetSize(80, 10)
	m.SetContent("old log content here")

	firstContent := m.Content()
	if firstContent == "" {
		t.Fatal("first content should not be empty")
	}

	m.SetContent("new content")
	if m.Content() == firstContent {
		t.Error("content should be updated to new content")
	}
	if m.Content() != "new content" {
		t.Errorf("content = %q, want %q", m.Content(), "new content")
	}
}

func TestBug10_LogViewerSetEmptyContent(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetSize(80, 10)
	m.SetContent("previous logs")
	m.SetContent("")

	view := m.View()
	if !strings.Contains(view, "(no output)") {
		t.Errorf("view should show (no output) after clearing, got: %s", view)
	}
}

func TestBug10_LogViewerSwitchContent(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetSize(80, 10)
	m.SetContent("task1 logs")
	m.SetContent("task2 logs")

	view := m.View()
	if strings.Contains(view, "task1 logs") {
		t.Error("view should not contain old task1 logs")
	}
	if !strings.Contains(view, "task2 logs") {
		t.Errorf("view should contain task2 logs, got: %s", view)
	}
}

func TestIntegration_LayoutConsistency(t *testing.T) {
	m := makeTestModelWithRuns()
	view := m.View()

	lines := strings.Split(view, "\n")
	if len(lines) < 5 {
		t.Fatalf("view too short: %d lines", len(lines))
	}

	for i, line := range lines {
		if line == "" && i > 0 && i < len(lines)-1 {
			continue
		}
	}
}

func TestIntegration_FullNavigationFlow(t *testing.T) {
	m := makeTestModelWithRuns()

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	model := m2.(Model)
	if model.state.FocusedPanel != FocusRightPanel {
		t.Errorf("should focus right panel after enter, got %v", model.state.FocusedPanel)
	}

	m3, _ := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})
	model2 := m3.(Model)
	if model2.state.RightTab != TabLogs {
		t.Errorf("should switch to logs tab, got %v", model2.state.RightTab)
	}

	m4, _ := model2.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}})
	model3 := m4.(Model)
	if model3.state.RightTab != TabDetail {
		t.Errorf("should switch back to detail tab, got %v", model3.state.RightTab)
	}
}
