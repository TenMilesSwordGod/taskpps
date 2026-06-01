package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
	testutil "github.com/taskpps/ppsctl/tui/testutil"
)

func TestBoundaryWindowSizeExtremeSmall(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 10, Height: 5}
	m2, _ := m.Update(msg)
	model := m2.(Model)

	view := model.View()
	if view == "" {
		t.Error("View should not panic and should produce output for 10x5")
	}
	for _, line := range strings.Split(view, "\n") {
		visualW := lipglossWidth(line)
		if visualW > 250 {
			limit := 50
			if len(line) < limit {
				limit = len(line)
			}
			t.Errorf("line visual width too large (%d) for small window: %q", visualW, line[:limit])
		}
	}
}

func TestBoundaryWindowSize20x8(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 20, Height: 8}
	m2, _ := m.Update(msg)
	model := m2.(Model)

	view := model.View()
	if view == "" {
		t.Error("View should not panic for 20x8")
	}
	if model.state.Dims.leftContentW < 0 {
		t.Error("leftContentW should not be negative")
	}
	if model.state.Dims.rightContentW < 0 {
		t.Error("rightContentW should not be negative")
	}
	if model.state.Dims.contentH < 0 {
		t.Error("contentH should not be negative")
	}
}

func TestBoundaryWindowSizeZero(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 0, Height: 0}
	m2, _ := m.Update(msg)
	model := m2.(Model)

	view := model.View()
	if view == "" {
		t.Error("View should produce degraded output for 0x0")
	}
}

func TestBoundaryWindowSizeMinimumEffective(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 42, Height: 10}
	m2, _ := m.Update(msg)
	model := m2.(Model)

	view := model.View()
	if view == "" {
		t.Error("View should render at minimum effective width 42")
	}
}

func TestBoundaryWindowSizeNormal(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 80, Height: 24}
	m2, _ := m.Update(msg)
	model := m2.(Model)

	if model.state.Dims.leftContentW <= 0 {
		t.Errorf("leftContentW = %d, want > 0", model.state.Dims.leftContentW)
	}
	if model.state.Dims.rightContentW <= 0 {
		t.Errorf("rightContentW = %d, want > 0", model.state.Dims.rightContentW)
	}
	leftPct := model.state.Dims.leftContentW * 100 / (model.state.Dims.leftContentW + model.state.Dims.rightContentW)
	if leftPct < 20 || leftPct > 40 {
		t.Errorf("left panel percentage = %d%%, expected around 28%%", leftPct)
	}
}

func TestBoundaryWindowSizeWide(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 240, Height: 60}
	m2, _ := m.Update(msg)
	model := m2.(Model)

	if model.state.Dims.leftContentW < 14 {
		t.Errorf("leftContentW = %d, want >= 14", model.state.Dims.leftContentW)
	}
	if model.state.Dims.rightContentW < 20 {
		t.Errorf("rightContentW = %d, want >= 20", model.state.Dims.rightContentW)
	}
}

func TestBoundaryDynamicResize(t *testing.T) {
	m := makeTestModel()
	sizes := []tea.WindowSizeMsg{
		{Width: 80, Height: 24},
		{Width: 20, Height: 8},
		{Width: 240, Height: 60},
		{Width: 80, Height: 24},
		{Width: 10, Height: 5},
		{Width: 200, Height: 50},
	}

	for i, size := range sizes {
		m2, _ := m.Update(size)
		m = m2.(Model)
		view := m.View()
		if view == "" {
			t.Errorf("View should render after resize step %d (size %dx%d)", i, size.Width, size.Height)
		}
	}
}

func TestBoundaryFirstResizeSetsReady(t *testing.T) {
	m := makeTestModel()
	if m.state.Ready {
		t.Error("model should not be ready before first WindowSizeMsg")
	}

	msg := tea.WindowSizeMsg{Width: 120, Height: 40}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if !model.state.Ready {
		t.Error("model should be ready after first WindowSizeMsg")
	}
}

func TestBoundarySingleColumnLayout(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 30
	m.state.Height = 20
	m.resizeComponents()

	view := m.View()
	if view == "" {
		t.Error("View should render even with width below single-column threshold")
	}
}

func TestBoundaryLongRunID(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	longRun := testutil.MakeLongIDRun()
	m.state.Runs = []models.Run{longRun}
	m.runList.SetRuns(m.state.Runs)

	view := m.runList.View()
	if view == "" {
		t.Error("RunList View should handle long IDs")
	}
	for _, line := range strings.Split(view, "\n") {
		visualW := lipglossWidth(line)
		if visualW > m.state.Dims.leftContentW+10 {
			t.Errorf("line overflows: visual width %d > content width %d", visualW, m.state.Dims.leftContentW)
		}
	}
}

func TestBoundaryLongPipelineName(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	longRun := testutil.MakeLongPipelineNameRun()
	m.state.Runs = []models.Run{longRun}
	m.runList.SetRuns(m.state.Runs)

	view := m.runList.View()
	if view == "" {
		t.Error("RunList View should handle long pipeline names")
	}
}

func TestBoundaryEmptyPipelineName(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	emptyRun := testutil.MakeEmptyPipelineNameRun()
	m.state.Runs = []models.Run{emptyRun}
	m.runList.SetRuns(m.state.Runs)

	view := m.runList.View()
	if view == "" {
		t.Error("RunList View should handle empty pipeline name")
	}
}

func TestBoundarySingleCharID(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	tinyRun := testutil.MakeSingleCharIDRun()
	m.state.Runs = []models.Run{tinyRun}
	m.runList.SetRuns(m.state.Runs)

	view := m.runList.View()
	if view == "" {
		t.Error("RunList View should handle single char ID")
	}
}

func TestBoundaryNilTasksSlice(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	run := models.Run{ID: "no-tasks", PipelineName: "test", Status: models.RunStatusRunning, Tasks: nil}
	m.state.Runs = []models.Run{run}
	m.runList.SetRuns(m.state.Runs)
	m.runDetail.SetRun(&run)

	detailView := m.runDetail.View()
	if detailView == "" {
		t.Error("RunDetail View should handle nil tasks")
	}
}

func TestBoundaryLongLogLine(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	longLine := testutil.MakeLongSingleLineLog(1000)
	m.logViewer.SetContent(longLine)
	m.logViewer.SetSize(80, 20)

	view := m.logViewer.View()
	if view == "" {
		t.Error("LogViewer should handle long single line")
	}
}

func TestBoundaryLongErrorMessage(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	m.state.ErrorMsg = strings.Repeat("E", 500)
	footer := renderFooter(120, m.state, &m)
	if footer == "" {
		t.Error("Footer should render with long error message")
	}
	if !strings.Contains(testutil.StripANSI(footer), "ERR:") {
		t.Error("Footer should contain ERR: prefix")
	}
}

func TestBoundaryFooterOverflow(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 60
	m.state.Height = 20
	m.resizeComponents()

	m.state.ErrorMsg = strings.Repeat("E", 500)
	m.state.Runs = testutil.MakeTestRuns()
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&m.state.Runs[0])

	footer := renderFooter(60, m.state, &m)
	if footer == "" {
		t.Error("Footer should render even when content overflows")
	}
}

func TestBoundaryMergeRunsEmptyExisting(t *testing.T) {
	newRuns := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
	}
	result := mergeRuns(nil, newRuns)
	if len(result) != 2 {
		t.Errorf("mergeRuns(nil, 2) = %d items, want 2", len(result))
	}
}

func TestBoundaryMergeRunsEmptyNew(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning, Tasks: []models.TaskRun{{TaskName: "t1"}}},
	}
	result := mergeRuns(existing, nil)
	if len(result) != 0 {
		t.Errorf("mergeRuns(1, nil) = %d items, want 0 (new runs replace all)", len(result))
	}
}

func TestBoundaryMergeRunsBothEmpty(t *testing.T) {
	result := mergeRuns(nil, nil)
	if len(result) != 0 {
		t.Errorf("mergeRuns(nil, nil) = %d items, want 0", len(result))
	}
}

func TestBoundaryMergeRunsNoOverlap(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", PipelineName: "old", Tasks: []models.TaskRun{{TaskName: "t1"}}},
	}
	newRuns := []models.Run{
		{ID: "r2", PipelineName: "new"},
		{ID: "r3", PipelineName: "newer"},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 2 {
		t.Errorf("mergeRuns no overlap = %d items, want 2", len(result))
	}
	for _, r := range result {
		if r.ID == "r1" {
			t.Error("r1 should not be in result since it's not in newRuns")
		}
	}
}

func TestBoundaryMergeRunsPartialOverlap(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning, Tasks: []models.TaskRun{{TaskName: "build"}, {TaskName: "test"}}},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess, Tasks: []models.TaskRun{{TaskName: "compile"}}},
	}
	newRuns := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusSuccess},
		{ID: "r3", PipelineName: "test", Status: models.RunStatusPending},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 2 {
		t.Errorf("mergeRuns partial overlap = %d items, want 2", len(result))
	}

	for _, r := range result {
		if r.ID == "r1" {
			if len(r.Tasks) != 2 {
				t.Errorf("r1 should preserve existing tasks, got %d", len(r.Tasks))
			}
			if r.Status != models.RunStatusSuccess {
				t.Errorf("r1 should have new status, got %s", r.Status)
			}
		}
	}
}

func TestBoundaryMergeRunsPreservesTasksWhenNewHasNone(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{{TaskName: "t1"}, {TaskName: "t2"}}},
	}
	newRuns := []models.Run{
		{ID: "r1", Tasks: nil},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatalf("expected 1 result, got %d", len(result))
	}
	if len(result[0].Tasks) != 2 {
		t.Errorf("should preserve existing tasks when new has none, got %d tasks", len(result[0].Tasks))
	}
}

func TestBoundaryStateMachineQuitView(t *testing.T) {
	m := makeTestModel()
	m.state.Quit = true
	view := m.View()
	if view != "" {
		t.Errorf("View should return empty string when quit=true, got %q", view)
	}
}

func TestBoundaryStateMachineNotReadyQuit(t *testing.T) {
	m := makeTestModel()
	if m.state.Ready {
		t.Error("model should not be ready initially")
	}

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if !model.state.Quit {
		t.Error("q key should quit even when not ready")
	}
}

func TestBoundaryStateMachineEmptyPipelinePN(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.Runs = nil

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.Quit {
		t.Error("p key on empty runs should not crash or quit")
	}

	msg = tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
	m3, _ := model.Update(msg)
	model2 := m3.(Model)
	if model2.state.Quit {
		t.Error("n key on empty runs should not crash or quit")
	}
}

func TestBoundaryStateMachineEmptyTaskEnter(t *testing.T) {
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
}

func TestBoundaryStateMachineEscMultiLayer(t *testing.T) {
	t.Run("esc_from_logs_to_detail", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs

		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.RightTab != TabDetail {
			t.Error("Esc from Logs should go to Detail")
		}
		if model.state.FocusedPanel != FocusRightPanel {
			t.Error("Esc from Logs should stay on RightPanel")
		}
	})

	t.Run("esc_from_detail_to_runlist", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail

		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("Esc from Detail should go to RunList")
		}
	})

	t.Run("esc_from_runlist_quits", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.FocusedPanel = FocusRunList

		msg := tea.KeyMsg{Type: tea.KeyEsc}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if !model.state.Quit {
			t.Error("Esc from RunList should quit")
		}
	})

	t.Run("full_esc_chain", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
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

func TestBoundaryRefreshKeyReturnsBothCmds(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.runDetail.SetRun(&models.Run{ID: "abc", PipelineName: "test", Status: models.RunStatusRunning})

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}}
	_, cmd := m.Update(msg)
	if cmd == nil {
		t.Error("r key should return batched commands (fetchRuns + fetchRun)")
	}
}

func TestBoundaryPanelFocusBoundary(t *testing.T) {
	t.Run("h_on_runlist_no_change", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRunList
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'h'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRunList {
			t.Error("h on RunList should not change focus")
		}
	})

	t.Run("l_on_rightpanel_no_change", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRightPanel
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if model.state.FocusedPanel != FocusRightPanel {
			t.Error("l on RightPanel should not change focus")
		}
	})
}

func TestBoundaryRunDetailCursorOverflow(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	m.runDetail.SetRun(&models.Run{
		ID:     "abc",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default"},
			{TaskName: "t2", SubpipelineName: "default"},
		},
	})

	m.runDetail.SetCursor(10)
	sel := m.runDetail.SelectedTask()
	if sel != nil {
		t.Error("cursor overflow should result in nil selected task")
	}
}

func TestBoundaryRunListCursorOverflow(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	runs := []models.Run{{ID: "r1"}, {ID: "r2"}}
	m.runList.SetRuns(runs)
	m.runList.SetCursor(5)

	sel := m.runList.SelectedRun()
	if sel == nil {
		t.Error("cursor should be clamped, SelectedRun should return valid run")
	}
}

func lipglossWidth(s string) int {
	w := 0
	inEscape := false
	for _, r := range s {
		if r == '\x1b' {
			inEscape = true
			continue
		}
		if inEscape {
			if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') {
				inEscape = false
			}
			continue
		}
		w++
	}
	return w
}
