package tui

import (
	"fmt"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
	"github.com/taskpps/ppsctl/models"
	testutil "github.com/taskpps/ppsctl/tui/testutil"

	"github.com/taskpps/ppsctl/tui/components"
)

func TestBugRunDetailSetSize0Panics(t *testing.T) {
	m := components.NewRunDetailModel()
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default", Status: models.TaskStatusRunning},
		},
	}
	m.SetRun(run)
	m.SetSize(80, 24)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("SetSize(0, h) with non-nil run caused panic: %v", r)
		}
	}()
	m.SetSize(0, 10)
	_ = m.View()
}

func TestBugRunDetailSetSize1Panics(t *testing.T) {
	m := components.NewRunDetailModel()
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default", Status: models.TaskStatusRunning},
		},
	}
	m.SetRun(run)
	m.SetSize(80, 24)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("SetSize(1, h) with non-nil run caused panic: %v", r)
		}
	}()
	m.SetSize(1, 10)
	_ = m.View()
}

func TestBugRunDetailNegativeWidthStringsRepeat(t *testing.T) {
	m := components.NewRunDetailModel()
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default", Status: models.TaskStatusRunning},
		},
	}
	m.SetRun(run)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RunDetail with negative internal width caused panic: %v", r)
		}
	}()
	m.SetSize(2, 10)
	_ = m.View()
}

func TestBugRunListSetSize0WidthOverflow(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{
		{ID: "r1", PipelineName: "very-long-pipeline-name-that-should-be-truncated", Status: models.RunStatusRunning},
	}
	m.SetRuns(runs)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("SetSize(0, h) caused panic: %v", r)
		}
	}()
	m.SetSize(0, 10)
	view := m.View()
	_ = view
}

func TestBugRunListSetSize1WidthOverflow(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{
		{ID: "r1", PipelineName: "pipeline", Status: models.RunStatusRunning},
	}
	m.SetRuns(runs)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("SetSize(1, h) caused panic: %v", r)
		}
	}()
	m.SetSize(1, 10)
	view := m.View()
	_ = view
}

func TestBugLogViewerSetSize0WidthOverflow(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("very long line that should be truncated but might overflow when width is 0")

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("SetSize(0, h) caused panic: %v", r)
		}
	}()
	m.SetSize(0, 10)
	view := m.View()
	_ = view
}

func TestBugRunListSetRunsEmptyDoesNotResetCursor(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{
		{ID: "r1"}, {ID: "r2"}, {ID: "r3"},
	}
	m.SetRuns(runs)
	m.SetCursor(2)
	m.SetSize(60, 10)

	m.SetRuns([]models.Run{})

	sel := m.SelectedRun()
	if sel != nil {
		t.Error("SelectedRun should be nil after setting empty runs")
	}

	m.SetRuns([]models.Run{{ID: "new1"}})
	sel = m.SelectedRun()
	if sel == nil {
		t.Error("SelectedRun should not be nil after setting new runs")
	}
	if sel.ID != "new1" {
		t.Errorf("cursor should be clamped to 0, got run %s", sel.ID)
	}
}

func TestBugMergeRunsDuplicateIDInExisting(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", PipelineName: "first", Tasks: []models.TaskRun{{TaskName: "task-from-first"}}},
		{ID: "r1", PipelineName: "second", Tasks: []models.TaskRun{{TaskName: "task-from-second"}}},
	}
	newRuns := []models.Run{
		{ID: "r1", PipelineName: "updated", Status: models.RunStatusRunning},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatalf("expected 1 result, got %d", len(result))
	}

	hasTask := len(result[0].Tasks) > 0
	if !hasTask {
		t.Error("mergeRuns should preserve at least one set of tasks from duplicate existing runs")
	}
}

func TestBugLogViewerSetContentEmptyShowsNoOutput(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("")
	view := m.View()
	if !strings.Contains(view, "(no output)") {
		t.Errorf("SetContent('') should show (no output), got: %q", view)
	}
}

func TestBugLogViewerSetContentThenEmptyShowsNoOutput(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("hello")
	m.SetContent("")
	view := m.View()
	if !strings.Contains(view, "(no output)") {
		t.Errorf("SetContent('') after content should show (no output), got: %q", view)
	}
}

func TestBugRunDetailUpdateEnterOnSubDoesNotAdjustCursor(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "group1"},
			{TaskName: "t2", SubpipelineName: "group1"},
			{TaskName: "t3", SubpipelineName: "group2"},
			{TaskName: "t4", SubpipelineName: "group2"},
		},
	}
	m.SetRun(run)

	m.SetCursor(0)
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	sel := m.SelectedTask()
	if sel != nil {
		t.Errorf("cursor on sub item should not select a task, got task %s", sel.TaskName)
	}
}

func TestBugRunDetailCollapseSubMovesCursorToSub(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "group1"},
			{TaskName: "t2", SubpipelineName: "group1"},
		},
	}
	m.SetRun(run)

	m.SetCursor(2)
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	sel := m.SelectedTask()
	_ = sel
}

func TestBugTruncateLineNegativeWidthReturnsFullLine(t *testing.T) {
	longLine := strings.Repeat("x", 200)
	result := components.TruncateLine(longLine, -1)
	if result == longLine {
		t.Error("TruncateLine with negative width should not return full untruncated line - this causes visual overflow")
	}
}

func TestBugProcessLineNegativeWidthReturnsFullLine(t *testing.T) {
	m := components.NewLogViewerModel()
	longLine := strings.Repeat("x", 200)
	m.SetContent(longLine)
	m.SetSize(0, 10)

	view := m.View()
	visualWidth := 0
	for _, r := range view {
		if r != '\n' && r != '\x1b' {
			visualWidth++
		}
	}
	if visualWidth > 200 {
		t.Error("LogViewer with width=0 should not show untruncated 200-char line")
	}
}

func TestBugRunDetailUpdateContentWithNegativeWidth(t *testing.T) {
	m := components.NewRunDetailModel()
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default", Status: models.TaskStatusRunning},
		},
	}
	m.SetRun(run)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RunDetail with width resulting in negative strings.Repeat caused panic: %v", r)
		}
	}()
	m.SetSize(3, 10)
	_ = m.View()
}

func TestBugResizeComponentsPassesZeroOrNegativeWidthToComponents(t *testing.T) {
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
}

func TestBugRunDetailMultipleSubGroupsSeparator(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "group1"},
			{TaskName: "t2", SubpipelineName: "group2"},
		},
	}
	m.SetRun(run)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RunDetail with multiple sub groups caused panic: %v", r)
		}
	}()

	m.SetSize(3, 10)
	_ = m.View()
}

func TestBugRunDetailWidth2StringsRepeat(t *testing.T) {
	m := components.NewRunDetailModel()
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{},
	}
	m.SetRun(run)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RunDetail with width=2 caused panic: %v", r)
		}
	}()
	m.SetSize(2, 10)
	_ = m.View()
}

func TestBugRunDetailWidth3StringsRepeat(t *testing.T) {
	m := components.NewRunDetailModel()
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{},
	}
	m.SetRun(run)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("RunDetail with width=3 caused panic: %v", r)
		}
	}()
	m.SetSize(3, 10)
	_ = m.View()
}

func TestBugViewWithZeroWidthNoPanic(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Runs = testutil.MakeTestRuns()
	m.runList.SetRuns(m.state.Runs)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("View with zero width caused panic: %v", r)
		}
	}()

	m.state.Width = 0
	m.state.Height = 10
	m.resizeComponents()
	_ = m.View()
}

func TestBugViewWithWidth1NoPanic(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Runs = testutil.MakeTestRuns()
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&m.state.Runs[0])

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("View with width=1 caused panic: %v", r)
		}
	}()

	m.state.Width = 1
	m.state.Height = 10
	m.resizeComponents()
	_ = m.View()
}

func TestBugMergeRunsPreservesOnlyLastDuplicateTasks(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{{TaskName: "task-A"}}},
		{ID: "r1", Tasks: []models.TaskRun{{TaskName: "task-B"}}},
	}
	newRuns := []models.Run{
		{ID: "r1", Status: models.RunStatusRunning},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatalf("expected 1 result, got %d", len(result))
	}

	if len(result[0].Tasks) == 0 {
		t.Error("tasks should be preserved from existing")
	} else {
		t.Logf("preserved task: %s (from last duplicate in existing)", result[0].Tasks[0].TaskName)
		if result[0].Tasks[0].TaskName == "task-A" {
			t.Error("BUG: only last duplicate's tasks are preserved, first duplicate's task-A is lost")
		}
	}
}

func TestBugRunListSetRunsEmptyThenNonEmpty(t *testing.T) {
	m := components.NewRunListModel()
	m.SetSize(60, 10)

	m.SetRuns([]models.Run{{ID: "r1"}, {ID: "r2"}, {ID: "r3"}})
	m.SetCursor(2)

	m.SetRuns([]models.Run{})
	if m.SelectedRun() != nil {
		t.Error("SelectedRun should be nil after empty SetRuns")
	}

	m.SetRuns([]models.Run{{ID: "new1"}, {ID: "new2"}})
	sel := m.SelectedRun()
	if sel == nil {
		t.Fatal("SelectedRun should not be nil after non-empty SetRuns")
	}
	if sel.ID != "new1" {
		t.Errorf("cursor should be clamped to valid index, got %s (cursor may be stale at %d)", sel.ID, 2)
	}
}

func TestBugRenderFooterWithZeroWidth(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	m := makeTestModel()
	m.state.Ready = true

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("renderFooter with width=0 caused panic: %v", r)
		}
	}()

	footer := renderFooter(0, m.state, &m)
	_ = footer
}

func TestBugRenderHeaderWithZeroWidth(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("renderHeader with width=0 caused panic: %v", r)
		}
	}()

	header := renderHeader(0)
	_ = header
}

func TestBugRenderTabsWithZeroWidth(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	defer func() {
		if r := recover(); r != nil {
			t.Errorf("renderTabs with width=0 caused panic: %v", r)
		}
	}()

	tabs := renderTabs(TabDetail, 0)
	_ = tabs
}

func TestBugFullViewChainWithExtremeSizes(t *testing.T) {
	sizes := []struct {
		w, h int
	}{
		{0, 0}, {1, 1}, {2, 2}, {3, 3}, {5, 5}, {10, 5}, {20, 8}, {42, 10},
	}

	for _, sz := range sizes {
		t.Run(fmt.Sprintf("%dx%d", sz.w, sz.h), func(t *testing.T) {
			m := makeTestModel()
			m.Update(tea.WindowSizeMsg{Width: sz.w, Height: sz.h})
			m.Update(runsFetchedMsg{runs: testutil.MakeTestRuns()})

			defer func() {
				if r := recover(); r != nil {
					t.Errorf("View chain at %dx%d caused panic: %v", sz.w, sz.h, r)
				}
			}()

			_ = m.View()
		})
	}
}
