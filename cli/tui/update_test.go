package tui

import (
	"errors"
	"fmt"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

func TestUpdateKeyQuit(t *testing.T) {
	keys := []string{"q", "ctrl+c"}
	for _, key := range keys {
		t.Run(key, func(t *testing.T) {
			m := makeTestModel()
			var msg tea.Msg
			switch key {
			case "q":
				msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}}
			case "ctrl+c":
				msg = tea.KeyMsg{Type: tea.KeyCtrlC}
			}
			m2, _ := m.Update(msg)
			model := m2.(Model)
			if !model.state.Quit {
				t.Errorf("quit should be true after %s", key)
			}
		})
	}
}

func TestUpdateEscKey(t *testing.T) {
	t.Run("esc_on_runlist_quits", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if !model.state.Quit {
			t.Error("esc on RunList should quit")
		}
	})

	t.Run("esc_on_rightpanel_navigates_back", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.Quit {
			t.Error("esc on RightPanel should not quit")
		}
		if model.state.RightTab != TabDetail {
			t.Error("esc on Logs tab should switch to Detail tab")
		}
	})

	t.Run("esc_on_detail_navigates_to_runlist", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("esc on Detail tab should focus RunList")
		}
	})

	t.Run("esc_full_chain", func(t *testing.T) {
		m := makeReadyModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs

		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyEsc})
		m = m2.(Model)
		if m.state.RightTab != TabDetail {
			t.Error("Step 1: Esc from Logs should go to Detail")
		}

		m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
		m = m2.(Model)
		if m.state.FocusedPanel != FocusRunList {
			t.Error("Step 2: Esc from Detail should go to RunList")
		}

		m2, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
		m = m2.(Model)
		if !m.state.Quit {
			t.Error("Step 3: Esc from RunList should quit")
		}
	})
}

func TestUpdateBackKey(t *testing.T) {
	t.Run("back_from_logs_to_detail", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.RightTab != TabDetail {
			t.Error("b from Logs should switch to Detail tab")
		}
	})

	t.Run("back_from_detail_to_runlist", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("b from Detail should focus RunList")
		}
	})

	t.Run("back_from_runlist_noop", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("b from RunList should not change focus")
		}
	})
}

func TestUpdateCollapseExpandKey(t *testing.T) {
	t.Run("c_collapses_expanded_tasks", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
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
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
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
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("c from RunList should not change anything")
		}
	})

	t.Run("c_noop_on_logs_tab", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.RightTab != TabLogs {
			t.Error("c from Logs tab should not change tab")
		}
	})
}

func TestUpdatePrevNextPipeline(t *testing.T) {
	runs := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
		{ID: "r3", PipelineName: "test", Status: models.RunStatusPending},
	}

	t.Run("prev_pipeline", func(t *testing.T) {
		m := makeReadyModelWithRuns(runs)
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runList.SetCursor(1)
		m.runDetail.SetRun(&runs[1])

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
		m := makeReadyModelWithRuns(runs)
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runList.SetCursor(1)
		m.runDetail.SetRun(&runs[1])

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
		m := makeReadyModelWithRuns(runs[:2])
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runList.SetCursor(0)
		m.runDetail.SetRun(&runs[0])

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r1" {
			t.Error("prev at first run should stay on r1")
		}
	})

	t.Run("next_at_last_noop", func(t *testing.T) {
		m := makeReadyModelWithRuns(runs[:2])
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runList.SetCursor(1)
		m.runDetail.SetRun(&runs[1])

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.runList.SelectedRun().ID != "r2" {
			t.Error("next at last run should stay on r2")
		}
	})

	t.Run("prev_next_from_runlist_noop", func(t *testing.T) {
		m := makeReadyModelWithRuns(runs[:2])
		m.state.FocusedPanel = FocusRunList
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

	t.Run("p_n_on_empty_runs_no_crash", func(t *testing.T) {
		m := makeReadyModel()
		m.state.FocusedPanel = FocusRightPanel
		m.state.Runs = nil

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
		m2, _ := m.Update(msg)
		if m2.(Model).state.Quit {
			t.Error("p key on empty runs should not crash or quit")
		}

		msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
		m3, _ := m2.(Model).Update(msg)
		if m3.(Model).state.Quit {
			t.Error("n key on empty runs should not crash or quit")
		}
	})
}

func TestUpdateTabFocus(t *testing.T) {
	m := makeTestModel()

	t.Run("tab_forward", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyTab}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRightPanel {
			t.Errorf("focus should be RightPanel after tab, got %v", model.state.FocusedPanel)
		}

		msg = tea.KeyMsg{Type: tea.KeyTab}
		m3, _ := model.Update(msg)
		model2 := m3.(Model)
		if model2.state.FocusedPanel != FocusRunList {
			t.Errorf("focus should be RunList after 2nd tab, got %v", model2.state.FocusedPanel)
		}
	})

	t.Run("shift_tab_backward", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyShiftTab}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRightPanel {
			t.Errorf("focus should be RightPanel after shift+tab, got %v", model.state.FocusedPanel)
		}
	})
}

func TestUpdateArrowKeys(t *testing.T) {
	m := makeTestModel()

	t.Run("right_from_runlist_no_focus_change", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRight}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Errorf("right should not change focus from RunList, got %v", model.state.FocusedPanel)
		}
	})

	t.Run("left_from_rightpanel_no_focus_change", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		msg := tea.KeyMsg{Type: tea.KeyLeft}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRightPanel {
			t.Errorf("left should not change focus from RightPanel, got %v", model.state.FocusedPanel)
		}
	})

	t.Run("vim_l_no_focus_change", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Errorf("vim l should not change focus, got %v", model.state.FocusedPanel)
		}
	})

	t.Run("vim_h_no_focus_change", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'h'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRightPanel {
			t.Errorf("vim h should not change focus, got %v", model.state.FocusedPanel)
		}
	})
}

func TestUpdateRefreshKey(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}}
	m2, cmd := m.Update(msg)
	_ = m2.(Model)
	if cmd == nil {
		t.Error("r key should return commands to refresh")
	}
}

func TestUpdateTKey(t *testing.T) {
	t.Run("t_switches_to_logs", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			ID:     "abc",
			Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusRunning},
			},
		})
		m.runDetail.SetCursor(1)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}}
		_, cmd := m.Update(msg)
		if cmd == nil {
			t.Error("t key on detail with task should dispatch fetchLogs")
		}
	})

	t.Run("t_switches_back_to_detail", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.RightTab != TabDetail {
			t.Error("t key on logs tab should switch back to Detail")
		}
	})

	t.Run("t_on_runlist_noop", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRunList
		m.state.Ready = true
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("t key on RunList should not change focus")
		}
	})
}

func TestUpdateEnterKey(t *testing.T) {
	t.Run("enter_on_runlist_with_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.Runs = []models.Run{
			{ID: "abc123", PipelineName: "deploy", Status: models.RunStatusRunning},
		}
		m.runList.SetRuns(m.state.Runs)
		m.runList.SetCursor(0)
		m.state.FocusedPanel = FocusRunList

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		m2, cmd := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRightPanel {
			t.Errorf("focus should move to RightPanel, got %v", model.state.FocusedPanel)
		}
		if cmd == nil {
			t.Error("enter on run should dispatch fetchRun")
		}
	})

	t.Run("enter_on_runlist_empty", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRunList

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("enter on RunList with no runs should not change focus")
		}
	})

	t.Run("enter_on_rightpanel_detail_with_task", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
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
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
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
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		_, _ = m.Update(msg)
	})

	t.Run("enter_on_empty_tasks_no_tab_switch", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runDetail.SetRun(&models.Run{ID: "abc", Status: models.RunStatusRunning, Tasks: nil})

		msg := tea.KeyMsg{Type: tea.KeyEnter}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.RightTab != TabDetail {
			t.Error("Enter on empty tasks should not switch tab")
		}
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
		if len(model.state.Runs) != 2 {
			t.Errorf("runs length = %d, want 2", len(model.state.Runs))
		}
		if model.state.ErrorMsg != "" {
			t.Errorf("errMsg = %q, want empty", model.state.ErrorMsg)
		}
	})

	t.Run("error", func(t *testing.T) {
		m := makeTestModel()
		msg := runsFetchedMsg{err: errors.New("connection refused")}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.ErrorMsg == "" {
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
		if model.state.FocusedPanel != FocusRightPanel {
			t.Errorf("should auto-focus on matching run, got %v", model.state.FocusedPanel)
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

	t.Run("same_hash_skips_update", func(t *testing.T) {
		m := makeTestModel()
		runs := []models.Run{
			{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
		}
		m.state.Runs = runs
		m.state.RunsHash = computeRunsHash(runs)

		msg := runsFetchedMsg{runs: runs}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if len(model.state.Runs) != 1 {
			t.Error("runs should remain unchanged")
		}
	})

	t.Run("merge_preserves_tasks", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusSuccess},
				{TaskName: "t2", Status: models.TaskStatusRunning},
			}},
		}
		m.runList.SetRuns(m.state.Runs)
		m.runList.SetCursor(0)
		m.runDetail.SetRun(&models.Run{ID: "r1"})

		newRun := &models.Run{ID: "r1", Tasks: nil, PipelineName: "updated"}
		msg := runFetchedMsg{run: newRun}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.Runs[0].PipelineName != "updated" {
			t.Error("run should be updated with fetched data")
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
		if model.state.ErrorMsg != "" {
			t.Errorf("errMsg = %q, want empty", model.state.ErrorMsg)
		}
	})

	t.Run("error", func(t *testing.T) {
		m := makeTestModel()
		msg := runFetchedMsg{err: errors.New("not found")}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.ErrorMsg == "" {
			t.Error("errMsg should be set on error")
		}
	})

	t.Run("nil_run", func(t *testing.T) {
		m := makeTestModel()
		msg := runFetchedMsg{run: nil}
		m2, _ := m.Update(msg)
		_ = m2.(Model)
	})

	t.Run("merge_into_runs_list", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.Runs = []models.Run{
			{ID: "r1", PipelineName: "old", Status: models.RunStatusPending,
				Tasks: []models.TaskRun{{TaskName: "existing", Status: models.TaskStatusSuccess}},
			},
			{ID: "r2", PipelineName: "keep", Status: models.RunStatusRunning},
		}
		m.state.RunsHash = "oldhash"

		newRun := &models.Run{ID: "r1", PipelineName: "updated", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{{TaskName: "newtask", Status: models.TaskStatusRunning}},
		}
		msg := runFetchedMsg{run: newRun}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if len(model.state.Runs) != 2 {
			t.Errorf("should have 2 runs, got %d", len(model.state.Runs))
		}
		if model.state.Runs[0].PipelineName != "updated" {
			t.Error("existing run should be updated in-place")
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
		if model.state.ErrorMsg != "" {
			t.Errorf("errMsg = %q, want empty", model.state.ErrorMsg)
		}
		content := model.logViewer.Content()
		if content == "" {
			t.Error("logViewer content should be set")
		}
	})

	t.Run("error", func(t *testing.T) {
		m := makeTestModel()
		msg := logsFetchedMsg{err: fmt.Errorf("test error")}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.ErrorMsg == "" {
			t.Error("should have error message")
		}
	})
}

func TestUpdateTickMsg(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	_ = m2.(Model)
	if cmd == nil {
		t.Error("tick should return refresh commands")
	}
}

func TestUpdateDebounceTick(t *testing.T) {
	m := makeTestModel()
	m.pendingRender = true
	msg := debounceTickMsg{}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	if model.pendingRender {
		t.Error("pendingRender should be false after debounce tick")
	}
	_ = cmd

	m.pendingRender = false
	msg2 := debounceTickMsg{}
	m3, cmd2 := m.Update(msg2)
	model2 := m3.(Model)
	if model2.pendingRender {
		t.Error("pendingRender should remain false")
	}
	_ = cmd2
}

func TestUpdateTickSkipDueToActivity(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.recordUserActivity()
	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	_ = m2.(Model)
	if cmd == nil {
		t.Error("tick should still return timer cmd even when skipping")
	}
}

func TestUpdateWindowSize(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 120, Height: 40}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.Width != 120 {
		t.Errorf("width = %d, want 120", model.state.Width)
	}
	if model.state.Height != 40 {
		t.Errorf("height = %d, want 40", model.state.Height)
	}
	if !model.state.Ready {
		t.Error("model should be ready after WindowSizeMsg")
	}
}

func TestUpdateWindowSizeAlreadyReady(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	msg := tea.WindowSizeMsg{Width: 80, Height: 24}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.Width != 80 {
		t.Errorf("width = %d, want 80", model.state.Width)
	}
	if model.state.Height != 24 {
		t.Errorf("height = %d, want 24", model.state.Height)
	}
}

func TestUpdateWindowSizeSmall(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 20, Height: 5}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if !model.state.Ready {
		t.Error("should be ready after small window resize")
	}
}

func TestDispatchKey(t *testing.T) {
	m := makeTestModel()

	t.Run("runlist_up", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		m.runList.SetRuns([]models.Run{{ID: "1"}, {ID: "2"}})
		m.runList.SetCursor(1)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyUp})
		if m.runList.SelectedRun() == nil {
			t.Error("RunList should have selection")
		}
	})

	t.Run("rundetail_down", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			Tasks: []models.TaskRun{
				{TaskName: "t1"}, {TaskName: "t2"},
			},
		})
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	})

	t.Run("logviewer_key", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'a'}}
		cmd := m.dispatchKey(msg)
		_ = cmd
	})

	t.Run("logviewer_pgdown", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		m.logViewer.SetContent("line1\nline2")
		m.logViewer.SetSize(80, 10)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyPgDown})
	})

	t.Run("rundetail_j_vim", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			Tasks: []models.TaskRun{
				{TaskName: "t1"}, {TaskName: "t2"},
			},
		})
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	})

	t.Run("detail_no_run_returns_nil", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
		_ = cmd
	})
}

func TestNavigatePrevPipelineEdgeCases(t *testing.T) {
	t.Run("empty_runs", func(t *testing.T) {
		m := makeTestModel()
		cmd := m.navigatePrevPipeline()
		if cmd != nil {
			t.Error("should return nil for empty runs")
		}
	})

	t.Run("nil_selected_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
		}
		cmd := m.navigatePrevPipeline()
		if cmd != nil {
			t.Error("should return nil when no run selected")
		}
	})

	t.Run("at_first_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
			{ID: "r2", Status: models.RunStatusSuccess},
		}
		m.runList.SetRuns(m.state.Runs)
		m.runList.SetCursor(0)
		m.runDetail.SetRun(&m.state.Runs[0])
		cmd := m.navigatePrevPipeline()
		if cmd != nil {
			t.Error("should return nil at first run")
		}
	})
}

func TestNavigateNextPipelineEdgeCases(t *testing.T) {
	t.Run("empty_runs", func(t *testing.T) {
		m := makeTestModel()
		cmd := m.navigateNextPipeline()
		if cmd != nil {
			t.Error("should return nil for empty runs")
		}
	})

	t.Run("nil_selected_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
		}
		cmd := m.navigateNextPipeline()
		if cmd != nil {
			t.Error("should return nil when no run selected")
		}
	})
}

func TestResizeComponents(t *testing.T) {
	t.Run("normal", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 150
		m.state.Height = 40
		m.resizeComponents()
		if m.runList.View() == "" {
			t.Error("RunList View should work after resize")
		}
		if m.runDetail.View() == "" {
			t.Error("RunDetail View should work after resize")
		}
	})

	t.Run("small_width", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 50
		m.state.Height = 30
		m.resizeComponents()
	})

	t.Run("very_small_width", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 30
		m.state.Height = 20
		m.resizeComponents()
	})

	t.Run("extremely_narrow", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 20
		m.state.Height = 10
		m.resizeComponents()
	})

	t.Run("zero_height", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 100
		m.state.Height = 0
		m.resizeComponents()
	})

	t.Run("large_window", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 300
		m.state.Height = 100
		m.resizeComponents()
		if m.state.Dims.innerW < 36 {
			t.Error("innerW should be reasonable")
		}
	})

	t.Run("medium_window", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 60
		m.state.Height = 15
		m.resizeComponents()
	})

	t.Run("available_height_clamped", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 80
		m.state.Height = 4
		m.resizeComponents()
	})

	t.Run("content_height_clamp", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 100
		m.state.Height = 4
		m.resizeComponents()
	})

	t.Run("total_content_clamp", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 37
		m.state.Height = 30
		m.resizeComponents()
	})

	t.Run("right_content_clamp", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 50
		m.state.Height = 30
		m.resizeComponents()
	})

	t.Run("exact_edge", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 39
		m.state.Height = 6
		m.resizeComponents()
	})

	t.Run("no_panic_with_zero_or_negative_width", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		defer func() {
			if r := recover(); r != nil {
				t.Errorf("resizeComponents with very small size caused panic: %v", r)
			}
		}()
		for w := 0; w <= 5; w++ {
			m.state.Width = w
			m.state.Height = 10
			m.resizeComponents()
			_ = m.View()
		}
	})

	t.Run("all_branches", func(t *testing.T) {
		tests := []struct {
			name   string
			width  int
			height int
		}{
			{"normal", 120, 40},
			{"small_available_height", 80, 3},
			{"medium", 60, 15},
			{"narrow_total_content", 38, 40},
			{"very_small", 20, 5},
			{"height_4_clamp_content", 80, 4},
			{"width_35_clamp_below_36", 35, 30},
			{"width_30_right_clamp", 30, 30},
		}
		for _, tc := range tests {
			t.Run(tc.name, func(t *testing.T) {
				m := makeTestModel()
				m.state.Width = tc.width
				m.state.Height = tc.height
				m.resizeComponents()
			})
		}
	})
}

func TestResizeSmallWidths(t *testing.T) {
	m := makeTestModel()

	t.Run("small_width_triggers_min", func(t *testing.T) {
		m.state.Width = 50
		m.state.Height = 30
		m.resizeComponents()
	})

	t.Run("very_small_width", func(t *testing.T) {
		m.state.Width = 30
		m.state.Height = 20
		m.resizeComponents()
	})
}

func TestCycleTab(t *testing.T) {
	m := makeTestModel()
	m.state.RightTab = TabDetail
	next := m.cycleTab()
	if next != TabLogs {
		t.Error("cycleTab from Detail should go to Logs")
	}

	m.state.RightTab = TabLogs
	next = m.cycleTab()
	if next != TabDetail {
		t.Error("cycleTab from Logs should go to Detail")
	}
}

func TestRecordUserActivity(t *testing.T) {
	m := makeTestModel()
	before := m.lastUserActivityTime
	m.recordUserActivity()
	if m.lastUserActivityTime == before {
		t.Error("recordUserActivity should update timestamp")
	}
}

func TestShouldSkipTick(t *testing.T) {
	m := makeTestModel()

	if m.shouldSkipTick() {
		t.Error("shouldSkipTick should be false when no activity")
	}

	m.recordUserActivity()
	if !m.shouldSkipTick() {
		t.Error("shouldSkipTick should be true right after activity")
	}
}

func TestRunDetailUpdatePreventsCrash(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "test",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning, SubpipelineName: "default"},
			{TaskName: "t2", Status: models.TaskStatusPending, SubpipelineName: "sub1"},
			{TaskName: "t3", Status: models.TaskStatusSuccess, SubpipelineName: "default"},
			{TaskName: "t4", Status: models.TaskStatusFailed, SubpipelineName: "sub2"},
			{TaskName: "t5", Status: models.TaskStatusSkipped, SubpipelineName: "default"},
			{TaskName: "t6", Status: models.TaskStatusCancelled, SubpipelineName: "sub1"},
		},
	})
	m.runDetail.SetSize(80, 24)

	for _, key := range []tea.KeyType{tea.KeyUp, tea.KeyDown, tea.KeyHome, tea.KeyEnd} {
		m.dispatchKey(tea.KeyMsg{Type: key})
	}
	m.View()
}

func TestNavBackFromDetail(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.navigateBack()
	if m.state.FocusedPanel != FocusRunList {
		t.Error("navigateBack from detail should go to RunList")
	}

	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.navigateBack()
	if m.state.RightTab != TabDetail {
		t.Error("navigateBack from logs should go to detail")
	}

	m.state.FocusedPanel = FocusRunList
	m.state.RightTab = TabDetail
	m.navigateBack()
	if m.state.FocusedPanel != FocusRunList {
		t.Error("navigateBack from RunList should stay")
	}
}

func TestTickMsgWithRunningTaskLogs(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runDetail.SetRun(&m.state.Runs[0])
	m.runDetail.SetCursor(1)
	m.runDetail.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})

	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	_ = m2.(Model)
	if cmd == nil {
		t.Error("tick with running task on logs tab should return commands")
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
