package tui

import (
	"errors"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/models"
)

func makeTestModel() Model {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	return NewModel(c, "")
}

func TestUpdateKeyQuit(t *testing.T) {
	keys := []string{"q", "ctrl+c"}
	for _, key := range keys {
		t.Run(key, func(t *testing.T) {
			m := makeTestModel()
			msg := tea.KeyMsg{}
			switch key {
			case "q":
				msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}}
			case "ctrl+c":
				msg = tea.KeyMsg{Type: tea.KeyCtrlC}
			}
			m2, _ := m.Update(msg)
			model := m2.(Model)
			if !model.quit {
				t.Errorf("quit should be true after %s", key)
			}
		})
	}
}

func TestUpdateEscKey(t *testing.T) {
	t.Run("esc_on_runlist_quits", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if !model.quit {
			t.Error("esc on RunList should quit")
		}
	})

	t.Run("esc_on_rightpanel_navigates_back", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.quit {
			t.Error("esc on RightPanel should not quit")
		}
		if model.rightTab != TabDetail {
			t.Error("esc on Logs tab should switch to Detail tab")
		}
	})

	t.Run("esc_on_detail_navigates_to_runlist", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRunList {
			t.Error("esc on Detail tab should focus RunList")
		}
	})
}

func TestUpdateBackKey(t *testing.T) {
	t.Run("back_from_logs_to_detail", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.rightTab != TabDetail {
			t.Error("b from Logs should switch to Detail tab")
		}
	})

	t.Run("back_from_detail_to_runlist", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRunList {
			t.Error("b from Detail should focus RunList")
		}
	})

	t.Run("back_from_runlist_noop", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRunList {
			t.Error("b from RunList should not change focus")
		}
	})
}

func TestUpdateCollapseExpandKey(t *testing.T) {
	t.Run("c_collapses_expanded_tasks", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusRunning},
				{TaskName: "t2", Status: models.TaskStatusPending},
			},
		})
		m.runDetail.ExpandAll()
		if !m.runDetail.HasExpanded() {
			t.Fatal("precondition: should have expanded tasks")
		}

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.runDetail.HasExpanded() {
			t.Error("c should collapse all expanded tasks")
		}
	})

	t.Run("c_expands_when_all_collapsed", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusRunning},
				{TaskName: "t2", Status: models.TaskStatusPending},
			},
		})
		m.runDetail.CollapseAll()
		if m.runDetail.HasExpanded() {
			t.Fatal("precondition: should have no expanded tasks")
		}

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if !model.runDetail.HasExpanded() {
			t.Error("c when all collapsed should expand all tasks")
		}
	})

	t.Run("c_noop_on_runlist", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRunList {
			t.Error("c from RunList should not change anything")
		}
	})

	t.Run("c_noop_on_logs_tab", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.rightTab != TabLogs {
			t.Error("c from Logs tab should not change tab")
		}
	})
}

func TestUpdatePrevNextPipeline(t *testing.T) {
	t.Run("prev_pipeline", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runs = []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
			{ID: "r3", PipelineName: "test", Status: models.RunStatusPending},
		}
		m.runList.SetRuns(m.runs)
		m.runList.SetCursor(1)
		m.runDetail.SetRun(&m.runs[1])

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
		m2, cmd := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r1" {
			t.Errorf("prev pipeline should select r1, got %s", model.runList.SelectedRun().ID)
		}
		if cmd == nil {
			t.Error("prev pipeline should dispatch fetchRun")
		}
	})

	t.Run("next_pipeline", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runs = []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
			{ID: "r3", PipelineName: "test", Status: models.RunStatusPending},
		}
		m.runList.SetRuns(m.runs)
		m.runList.SetCursor(1)
		m.runDetail.SetRun(&m.runs[1])

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
		m2, cmd := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r3" {
			t.Errorf("next pipeline should select r3, got %s", model.runList.SelectedRun().ID)
		}
		if cmd == nil {
			t.Error("next pipeline should dispatch fetchRun")
		}
	})

	t.Run("prev_at_first_noop", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runs = []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		}
		m.runList.SetRuns(m.runs)
		m.runList.SetCursor(0)
		m.runDetail.SetRun(&m.runs[0])

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r1" {
			t.Error("prev at first run should stay on r1")
		}
	})

	t.Run("next_at_last_noop", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runs = []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		}
		m.runList.SetRuns(m.runs)
		m.runList.SetCursor(1)
		m.runDetail.SetRun(&m.runs[1])

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r2" {
			t.Error("next at last run should stay on r2")
		}
	})

	t.Run("prev_next_from_runlist_noop", func(t *testing.T) {
		m := makeTestModel()
		m.focusedPanel = FocusRunList
		m.runs = []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		}
		m.runList.SetRuns(m.runs)
		m.runList.SetCursor(1)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r2" {
			t.Error("p from RunList should not change selection")
		}

		msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
		m3, _ := model.Update(msg)
		model2 := m3.(Model)
		if model2.runList.SelectedRun().ID != "r2" {
			t.Error("n from RunList should not change selection")
		}
	})
}

func TestUpdateTabFocus(t *testing.T) {
	m := makeTestModel()

	t.Run("tab_forward", func(t *testing.T) {
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyTab}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRightPanel {
			t.Errorf("focus should be RightPanel after tab, got %v", model.focusedPanel)
		}

		msg = tea.KeyMsg{Type: tea.KeyTab}
		m3, _ := model.Update(msg)
		model2 := m3.(Model)
		if model2.focusedPanel != FocusRunList {
			t.Errorf("focus should be RunList after 2nd tab, got %v", model2.focusedPanel)
		}
	})

	t.Run("shift_tab_backward", func(t *testing.T) {
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyShiftTab}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRightPanel {
			t.Errorf("focus should be RightPanel after shift+tab, got %v", model.focusedPanel)
		}
	})
}

func TestUpdateArrowKeys(t *testing.T) {
	m := makeTestModel()

	t.Run("right_from_runlist_no_focus_change", func(t *testing.T) {
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRight}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRunList {
			t.Errorf("right should not change focus from RunList, got %v", model.focusedPanel)
		}
	})

	t.Run("left_from_rightpanel_no_focus_change", func(t *testing.T) {
		m.focusedPanel = FocusRightPanel
		msg := tea.KeyMsg{Type: tea.KeyLeft}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRightPanel {
			t.Errorf("left should not change focus from RightPanel, got %v", model.focusedPanel)
		}
	})

	t.Run("vim_l_no_focus_change", func(t *testing.T) {
		m.focusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRunList {
			t.Errorf("vim l should not change focus, got %v", model.focusedPanel)
		}
	})

	t.Run("vim_h_no_focus_change", func(t *testing.T) {
		m.focusedPanel = FocusRightPanel
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'h'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRightPanel {
			t.Errorf("vim h should not change focus, got %v", model.focusedPanel)
		}
	})
}

func TestUpdateRefreshKey(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	_ = model
	if cmd == nil {
		t.Error("r key should return commands to refresh")
	}
}

func TestUpdateEnterKey(t *testing.T) {
	t.Run("enter_on_runlist_with_run", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.runs = []models.Run{
			{ID: "abc123", PipelineName: "deploy", Status: models.RunStatusRunning},
		}
		m.runList.SetRuns(m.runs)
		m.runList.SetCursor(0)
		m.focusedPanel = FocusRunList

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		m2, cmd := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRightPanel {
			t.Errorf("focus should move to RightPanel, got %v", model.focusedPanel)
		}
		if cmd == nil {
			t.Error("enter on run should dispatch fetchRun")
		}
	})

	t.Run("enter_on_runlist_empty", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRunList

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		_ = model
	})

	t.Run("enter_on_rightpanel_detail", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "test", Status: models.TaskStatusRunning},
			},
		})
		m.runDetail.SetCursor(1)

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		_, cmd := m.Update(msg)
		if cmd == nil {
			t.Error("enter on RightPanel should dispatch command")
		}
	})

	t.Run("enter_on_rightpanel_no_task", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks:  []models.TaskRun{},
		})

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		_, _ = m.Update(msg)
	})

	t.Run("enter_on_rightpanel_logs", func(t *testing.T) {
		m := makeTestModel()
		m.ready = true
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabLogs

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		_, _ = m.Update(msg)
	})
}

func TestUpdateRunsFetched(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		m := makeTestModel()
		runs := []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		}
		msg := runsFetchedMsg{runs: runs}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if len(model.runs) != 2 {
			t.Errorf("runs length = %d, want 2", len(model.runs))
		}
		if model.errMsg != "" {
			t.Errorf("errMsg = %q, want empty", model.errMsg)
		}
	})

	t.Run("error", func(t *testing.T) {
		m := makeTestModel()
		msg := runsFetchedMsg{err: errors.New("connection refused")}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.errMsg == "" {
			t.Error("errMsg should be set on error")
		}
	})

	t.Run("with_target_run", func(t *testing.T) {
		m := makeTestModel()
		m.targetRunID = "r2"
		runs := []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusPending},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusRunning},
		}
		msg := runsFetchedMsg{runs: runs}
		m2, cmd := m.Update(msg)
		model := m2.(Model)
		if model.focusedPanel != FocusRightPanel {
			t.Errorf("should auto-focus on matching run, got %v", model.focusedPanel)
		}
		if cmd == nil {
			t.Error("should dispatch fetchRun for matched run")
		}
		if model.targetRunID != "" {
			t.Errorf("targetRunID should be cleared, got %q", model.targetRunID)
		}
	})

	t.Run("target_run_not_found", func(t *testing.T) {
		m := makeTestModel()
		m.targetRunID = "nonexistent"
		runs := []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		}
		msg := runsFetchedMsg{runs: runs}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.targetRunID != "nonexistent" {
			t.Error("targetRunID should not be cleared if not found")
		}
	})
}

func TestUpdateRunFetched(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		m := makeTestModel()
		run := &models.Run{ID: "abc", PipelineName: "deploy", Status: models.RunStatusRunning}
		msg := runFetchedMsg{run: run}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.errMsg != "" {
			t.Errorf("errMsg = %q, want empty", model.errMsg)
		}
	})

	t.Run("error", func(t *testing.T) {
		m := makeTestModel()
		msg := runFetchedMsg{err: errors.New("not found")}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.errMsg == "" {
			t.Error("errMsg should be set on error")
		}
	})
}

func TestUpdateLogsFetched(t *testing.T) {
	t.Run("success", func(t *testing.T) {
		m := makeTestModel()
		logs := map[string]string{"task1": "line1\nline2"}
		msg := logsFetchedMsg{logs: logs}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.errMsg != "" {
			t.Errorf("errMsg = %q, want empty", model.errMsg)
		}
		content := model.logViewer.Content()
		if content == "" {
			t.Error("logViewer content should be set")
		}
	})

	t.Run("error", func(t *testing.T) {
		m := makeTestModel()
		msg := logsFetchedMsg{err: errors.New("timeout")}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		content := model.logViewer.Content()
		if content == "" {
			t.Error("logViewer should show error content")
		}
	})
}

func TestUpdateTickMsg(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	_ = model
	if cmd == nil {
		t.Error("tick should return refresh commands")
	}
}

func TestUpdateWindowSize(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 120, Height: 40}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.width != 120 {
		t.Errorf("width = %d, want 120", model.width)
	}
	if model.height != 40 {
		t.Errorf("height = %d, want 40", model.height)
	}
	if !model.ready {
		t.Error("model should be ready after WindowSizeMsg")
	}
}

func TestDispatchKey(t *testing.T) {
	m := makeTestModel()

	t.Run("runlist_up", func(t *testing.T) {
		m.focusedPanel = FocusRunList
		m.runList.SetRuns([]models.Run{{ID: "1"}, {ID: "2"}})
		m.runList.SetCursor(1)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyUp})
		if m.runList.SelectedRun() == nil {
			t.Error("RunList should have selection")
		}
	})

	t.Run("rundetail_down", func(t *testing.T) {
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			Tasks: []models.TaskRun{
				{TaskName: "t1"}, {TaskName: "t2"},
			},
		})
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	})

	t.Run("logviewer_key", func(t *testing.T) {
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'a'}}
		cmd := m.dispatchKey(msg)
		_ = cmd
	})

	t.Run("logviewer_pgdown", func(t *testing.T) {
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabLogs
		m.logViewer.SetContent("line1\nline2")
		m.logViewer.SetSize(80, 10)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyPgDown})
	})

	t.Run("rundetail_j_vim", func(t *testing.T) {
		m.focusedPanel = FocusRightPanel
		m.rightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			Tasks: []models.TaskRun{
				{TaskName: "t1"}, {TaskName: "t2"},
			},
		})
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	})
}

func TestResizeSmallWidths(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")

	t.Run("small_width_triggers_min", func(t *testing.T) {
		m.width = 50
		m.height = 30
		m.resizeComponents()
	})

	t.Run("very_small_width", func(t *testing.T) {
		m.width = 30
		m.height = 20
		m.resizeComponents()
	})
}
