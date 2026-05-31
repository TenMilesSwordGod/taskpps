package tui

import (
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
)

func TestIntegrationBrowseRunList(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		{ID: "r3", PipelineName: "test", Status: models.RunStatusPending},
	}
	m.runs = runs
	m.runList.SetRuns(runs)

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = m2.(Model)
	if m.runList.SelectedRun().ID != "r2" {
		t.Error("down should move to r2")
	}

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m = m2.(Model)
	if m.runList.SelectedRun().ID != "r3" {
		t.Error("second down should move to r3")
	}

	m2, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = m2.(Model)
	if m.focusedPanel != FocusRightPanel {
		t.Error("enter should move focus to RightPanel")
	}
	if cmd == nil {
		t.Error("enter should dispatch fetchRun")
	}
	if m.runDetail.SelectedRun() == nil || m.runDetail.SelectedRun().ID != "r3" {
		t.Error("runDetail should show r3")
	}
}

func TestIntegrationTabSwitching(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{{TaskName: "build", SubpipelineName: "default", Status: models.TaskStatusRunning}}},
	}
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})
	m = m2.(Model)
	if m.rightTab != TabLogs {
		t.Error("t should switch to Logs tab")
	}

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})
	m = m2.(Model)
	if m.rightTab != TabDetail {
		t.Error("second t should switch back to Detail tab")
	}
}

func TestIntegrationCollapseExpand(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	run := models.Run{
		ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "build", SubpipelineName: "default", Status: models.TaskStatusRunning},
			{TaskName: "test", SubpipelineName: "default", Status: models.TaskStatusPending},
		},
	}
	m.runs = []models.Run{run}
	m.runList.SetRuns(m.runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&run)
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail

	if m.runDetail.HasExpanded() {
		t.Error("tasks should start collapsed by default")
	}

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}})
	m = m2.(Model)
	if !m.runDetail.HasExpanded() {
		t.Error("c should expand all tasks when collapsed")
	}

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}})
	m = m2.(Model)
	if m.runDetail.HasExpanded() {
		t.Error("c should collapse all tasks when expanded")
	}
}

func TestIntegrationLogScrolling(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	m.logViewer.SetContent("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10\nline11\nline12\nline13\nline14\nline15\nline16\nline17\nline18\nline19\nline20")
	m.logViewer.SetSize(80, 10)
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabLogs

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyPgDown})
	m = m2.(Model)

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyPgDown})
	m = m2.(Model)

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyPgUp})
	m = m2.(Model)

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyHome})
	m = m2.(Model)

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyEnd})
	m = m2.(Model)

	view := m.logViewer.View()
	if view == "" {
		t.Error("log viewer should have content after scrolling")
	}
}

func TestIntegrationPipelineNavigation(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		{ID: "r3", PipelineName: "test", Status: models.RunStatusPending},
	}
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(1)
	m.runDetail.SetRun(&runs[1])
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail

	m2, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}})
	m = m2.(Model)
	if m.runList.SelectedRun().ID != "r3" {
		t.Error("n should navigate to next pipeline")
	}
	if cmd == nil {
		t.Error("n should dispatch fetchRun")
	}

	m2, cmd = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}})
	m = m2.(Model)
	if m.runList.SelectedRun().ID != "r2" {
		t.Error("p should navigate to prev pipeline")
	}
	if cmd == nil {
		t.Error("p should dispatch fetchRun")
	}
}

func TestIntegrationEscMultiLayer(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning}}
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabLogs

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = m2.(Model)
	if m.rightTab != TabDetail {
		t.Error("Esc from Logs should go to Detail")
	}

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = m2.(Model)
	if m.focusedPanel != FocusRunList {
		t.Error("Esc from Detail should go to RunList")
	}

	m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	m = m2.(Model)
	if !m.quit {
		t.Error("Esc from RunList should quit")
	}
}

func TestIntegrationRefreshFlow(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning}}
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])

	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}})
	if cmd == nil {
		t.Error("r should return refresh commands")
	}
}

func TestIntegrationErrorRecovery(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	m2, _ := m.Update(runsFetchedMsg{err: &testError{msg: "connection refused"}})
	m = m2.(Model)
	if m.errMsg == "" {
		t.Error("error should be set")
	}

	m2, _ = m.Update(runsFetchedMsg{runs: []models.Run{{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning}}})
	m = m2.(Model)
	if m.errMsg != "" {
		t.Error("successful fetch should clear error")
	}
	if len(m.runs) != 1 {
		t.Error("successful fetch should set runs")
	}
}

func TestIntegrationAutoFocusTargetRun(t *testing.T) {
	m := makeTestModel()
	m.targetRunID = "r2"

	runs := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
	}

	m2, cmd := m.Update(runsFetchedMsg{runs: runs})
	m = m2.(Model)
	if m.focusedPanel != FocusRightPanel {
		t.Error("should auto-focus on target run")
	}
	if m.runList.SelectedRun() == nil || m.runList.SelectedRun().ID != "r2" {
		t.Error("should select target run")
	}
	if cmd == nil {
		t.Error("should dispatch fetchRun for target")
	}
	if m.targetRunID != "" {
		t.Error("targetRunID should be cleared after match")
	}
}

func TestIntegrationTargetRunNotFound(t *testing.T) {
	m := makeTestModel()
	m.targetRunID = "missing"

	runs := []models.Run{{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning}}
	m2, _ := m.Update(runsFetchedMsg{runs: runs})
	m = m2.(Model)
	if m.targetRunID != "missing" {
		t.Error("targetRunID should be preserved when not found")
	}
	if m.focusedPanel != FocusRunList {
		t.Error("should stay on RunList when target not found")
	}
}

func TestIntegrationEnterOnRightPanelDetail(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	run := models.Run{
		ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "build", SubpipelineName: "default", Status: models.TaskStatusRunning},
		},
	}
	m.runs = []models.Run{run}
	m.runList.SetRuns(m.runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&run)
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail

	m.runDetail.SetCursor(1)

	m2, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})
	m = m2.(Model)
	if cmd == nil {
		t.Error("enter on task should dispatch command")
	}
	if m.rightTab != TabLogs {
		t.Error("enter on task should switch to Logs tab")
	}
}

type testError struct {
	msg string
}

func (e *testError) Error() string {
	return e.msg
}
