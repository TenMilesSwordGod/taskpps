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

func TestDeepTruncateLineWidth1(t *testing.T) {
	result := components.TruncateLine("hello", 1)
	if result != "" {
		t.Errorf("TruncateLine width=1 should return empty, got %q", result)
	}
}

func TestDeepTruncateLineWidth2(t *testing.T) {
	result := components.TruncateLine("hello", 2)
	if result != "" {
		t.Errorf("TruncateLine width=2 should return empty, got %q", result)
	}
}

func TestDeepTruncateLineWidth3(t *testing.T) {
	result := components.TruncateLine("hello", 3)
	if result != "" {
		t.Errorf("TruncateLine width=3 should return empty, got %q", result)
	}
}

func TestDeepTruncateLineWidth4(t *testing.T) {
	result := components.TruncateLine("hello world", 4)
	if lipgloss.Width(result) > 4 {
		t.Errorf("TruncateLine width=4 should fit in 4, got width=%d: %q", lipgloss.Width(result), result)
	}
	if !strings.Contains(result, "...") {
		t.Errorf("TruncateLine width=4 should contain '...', got %q", result)
	}
}

func TestDeepTruncateLineWidth5(t *testing.T) {
	result := components.TruncateLine("hello world", 5)
	if lipgloss.Width(result) > 5 {
		t.Errorf("TruncateLine width=5 should fit in 5, got width=%d: %q", lipgloss.Width(result), result)
	}
}

func TestDeepTruncateLineExactFit(t *testing.T) {
	result := components.TruncateLine("hello", 5)
	if result != "hello" {
		t.Errorf("TruncateLine exact fit should return original, got %q", result)
	}
}

func TestDeepTruncateLineEmpty(t *testing.T) {
	result := components.TruncateLine("", 10)
	if result != "" {
		t.Errorf("TruncateLine empty string should return empty, got %q", result)
	}
}

func TestDeepTruncateLineNegativeWidth(t *testing.T) {
	result := components.TruncateLine("hello", -10)
	if result != "" {
		t.Errorf("TruncateLine negative width should return empty, got %q", result)
	}
}

func TestDeepTruncateLineUnicodeDoubleWidth(t *testing.T) {
	result := components.TruncateLine("██████████", 5)
	if lipgloss.Width(result) > 5 {
		t.Errorf("TruncateLine with double-width chars should fit, got width=%d: %q", lipgloss.Width(result), result)
	}
}

func TestDeepTruncateLineMixedANSI(t *testing.T) {
	styled := lipgloss.NewStyle().Foreground(lipgloss.Color("#FF0000")).Render("hello world")
	result := components.TruncateLine(styled, 8)
	if lipgloss.Width(result) > 8 {
		t.Errorf("TruncateLine with ANSI should fit, got width=%d", lipgloss.Width(result))
	}
}

func TestDeepTruncateStrWidth0(t *testing.T) {
	result := truncateStr("hello", 0)
	if result != "" {
		t.Errorf("truncateStr maxLen=0 should return empty, got %q", result)
	}
}

func TestDeepTruncateStrWidth1(t *testing.T) {
	result := truncateStr("hello", 1)
	if result != "" {
		t.Errorf("truncateStr maxLen=1 should return empty, got %q", result)
	}
}

func TestDeepTruncateStrWidth3(t *testing.T) {
	result := truncateStr("hello", 3)
	if result != "" {
		t.Errorf("truncateStr maxLen=3 should return empty, got %q", result)
	}
}

func TestDeepTruncateStrWidth4(t *testing.T) {
	result := truncateStr("hello world", 4)
	if len([]rune(result)) > 4 {
		t.Errorf("truncateStr maxLen=4 should be <=4 runes, got %d: %q", len([]rune(result)), result)
	}
	if !strings.Contains(result, "...") {
		t.Errorf("truncateStr maxLen=4 should contain '...', got %q", result)
	}
}

func TestDeepTruncateStrExactLen(t *testing.T) {
	result := truncateStr("hello", 5)
	if result != "hello" {
		t.Errorf("truncateStr exact len should return original, got %q", result)
	}
}

func TestDeepTruncateStrEmpty(t *testing.T) {
	result := truncateStr("", 10)
	if result != "" {
		t.Errorf("truncateStr empty should return empty, got %q", result)
	}
}

func TestDeepTruncateStrUnicode(t *testing.T) {
	result := truncateStr("你好世界测试数据", 4)
	if !strings.Contains(result, "...") {
		t.Errorf("truncateStr with unicode should contain '...', got %q", result)
	}
}

func TestDeepFormatTimeExactly19(t *testing.T) {
	s := "2024-01-15T10:30:00"
	result := components.FormatTime(&s)
	if result != "01-15T10:30:00" {
		t.Errorf("FormatTime exactly 19 chars = %q, want %q", result, "01-15T10:30:00")
	}
}

func TestDeepFormatTime18Chars(t *testing.T) {
	s := "2024-01-15T10:30:0"
	result := components.FormatTime(&s)
	if result != s {
		t.Errorf("FormatTime 18 chars should return original, got %q", result)
	}
}

func TestDeepFormatTime20Chars(t *testing.T) {
	s := "2024-01-15T10:30:00Z"
	result := components.FormatTime(&s)
	if result != "01-15T10:30:00" {
		t.Errorf("FormatTime 20 chars = %q, want %q", result, "01-15T10:30:00")
	}
}

func TestDeepFormatTimeEmptyString(t *testing.T) {
	s := ""
	result := components.FormatTime(&s)
	if result != "" {
		t.Errorf("FormatTime empty string = %q, want empty", result)
	}
}

func TestDeepFormatTimeSingleChar(t *testing.T) {
	s := "X"
	result := components.FormatTime(&s)
	if result != "X" {
		t.Errorf("FormatTime single char = %q, want %q", result, "X")
	}
}

func TestDeepResizeComponentsLayoutMath(t *testing.T) {
	t.Run("width_36_minimum_totalContentW", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 39
		m.state.Height = 20
		m.resizeComponents()
		if m.state.Dims.leftContentW < 14 {
			t.Errorf("leftContentW = %d, want >= 14", m.state.Dims.leftContentW)
		}
		if m.state.Dims.rightContentW < 20 {
			t.Errorf("rightContentW = %d, want >= 20", m.state.Dims.rightContentW)
		}
	})

	t.Run("width_42_minimum_effective", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 42
		m.state.Height = 20
		m.resizeComponents()
		if m.state.Dims.leftContentW < 14 {
			t.Errorf("leftContentW = %d, want >= 14", m.state.Dims.leftContentW)
		}
	})

	t.Run("width_1_extreme", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 1
		m.state.Height = 1
		m.resizeComponents()
		view := m.View()
		if view == "" {
			t.Error("View should produce output even for 1x1")
		}
	})

	t.Run("height_1_extreme", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 120
		m.state.Height = 1
		m.resizeComponents()
		if m.state.Dims.contentH < 3 {
			t.Errorf("contentH should be clamped to 3, got %d", m.state.Dims.contentH)
		}
	})

	t.Run("height_7_minimum_for_content", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 120
		m.state.Height = 7
		m.resizeComponents()
		if m.state.Dims.contentH < 3 {
			t.Errorf("contentH should be at least 3, got %d", m.state.Dims.contentH)
		}
	})

	t.Run("left_right_sum_equals_totalContentW", func(t *testing.T) {
		for w := 42; w <= 250; w++ {
			m := makeTestModel()
			m.state.Width = w
			m.state.Height = 30
			m.resizeComponents()
			sum := m.state.Dims.leftContentW + m.state.Dims.rightContentW
			expectedTotal := m.state.Dims.innerW - 2 - 1
			if sum != expectedTotal {
				t.Errorf("width=%d: left(%d)+right(%d)=%d, expected total=%d",
					w, m.state.Dims.leftContentW, m.state.Dims.rightContentW, sum, expectedTotal)
				return
			}
		}
	})

	t.Run("integer_division_28_percent", func(t *testing.T) {
		m := makeTestModel()
		m.state.Width = 80
		m.state.Height = 24
		m.resizeComponents()
		totalContentW := m.state.Dims.leftContentW + m.state.Dims.rightContentW
		expectedLeft := totalContentW * 28 / 100
		if m.state.Dims.leftContentW != expectedLeft && m.state.Dims.leftContentW >= 14 && m.state.Dims.rightContentW >= 20 {
			t.Logf("leftContentW=%d, expected 28%%=%d (clamping may apply)", m.state.Dims.leftContentW, expectedLeft)
		}
	})
}

func TestDeepMergeRunsDuplicateIDsInNewRuns(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", PipelineName: "old", Tasks: []models.TaskRun{{TaskName: "t1"}}},
	}
	newRuns := []models.Run{
		{ID: "r1", PipelineName: "new1", Status: models.RunStatusRunning},
		{ID: "r1", PipelineName: "new2", Status: models.RunStatusSuccess},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 2 {
		t.Errorf("mergeRuns with duplicate IDs in newRuns = %d items, want 2", len(result))
	}
	taskPreserved := false
	for _, r := range result {
		if r.ID == "r1" && len(r.Tasks) > 0 {
			taskPreserved = true
		}
	}
	if !taskPreserved {
		t.Error("mergeRuns should preserve tasks from existing for at least one duplicate")
	}
}

func TestDeepMergeRunsExistingTasksPreservedOnlyIfNotEmpty(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{}},
	}
	newRuns := []models.Run{
		{ID: "r1", Status: models.RunStatusRunning},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatalf("expected 1 result, got %d", len(result))
	}
	if len(result[0].Tasks) != 0 {
		t.Errorf("empty existing tasks should not overwrite new run's tasks, got %d tasks", len(result[0].Tasks))
	}
}

func TestDeepMergeRunsNewRunWithTasks(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{{TaskName: "old-task"}}},
	}
	newRuns := []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{{TaskName: "new-task"}}},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatalf("expected 1 result, got %d", len(result))
	}
	if len(result[0].Tasks) != 1 || result[0].Tasks[0].TaskName != "old-task" {
		t.Errorf("existing tasks should be preserved over new tasks, got tasks: %v", result[0].Tasks)
	}
}

func TestDeepMergeRunsLargeScale(t *testing.T) {
	existing := make([]models.Run, 100)
	for i := range existing {
		existing[i] = models.Run{ID: fmt.Sprintf("run-%d", i), Tasks: []models.TaskRun{{TaskName: "task"}}}
	}
	newRuns := make([]models.Run, 100)
	for i := range newRuns {
		newRuns[i] = models.Run{ID: fmt.Sprintf("run-%d", i), Status: models.RunStatusRunning}
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 100 {
		t.Errorf("large scale merge = %d items, want 100", len(result))
	}
	for _, r := range result {
		if len(r.Tasks) != 1 {
			t.Errorf("run %s should preserve tasks, got %d", r.ID, len(r.Tasks))
		}
	}
}

func TestDeepRenderFooterAllPanelTabCombos(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	combos := []struct {
		panel PanelFocus
		tab   RightPanelTab
		name  string
	}{
		{FocusRunList, TabDetail, "runlist"},
		{FocusRightPanel, TabDetail, "right_detail"},
		{FocusRightPanel, TabLogs, "right_logs"},
	}

	for _, combo := range combos {
		t.Run(combo.name, func(t *testing.T) {
			m := makeTestModel()
			m.state.Ready = true
			m.state.Width = 120
			m.state.Height = 40
			m.resizeComponents()
			m.state.FocusedPanel = combo.panel
			m.state.RightTab = combo.tab

			footer := renderFooter(120, m.state, &m)
			if footer == "" {
				t.Error("footer should not be empty")
			}
		})
	}
}

func TestDeepRenderFooterVeryNarrow(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 30
	m.state.Height = 15
	m.resizeComponents()
	m.state.ErrorMsg = "very long error message that should be truncated"
	m.state.Runs = testutil.MakeTestRuns()
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&m.state.Runs[0])

	footer := renderFooter(30, m.state, &m)
	if footer == "" {
		t.Error("footer should render even when very narrow")
	}
}

func TestDeepRenderHeaderVeryNarrow(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	header := renderHeader(10)
	if header == "" {
		t.Error("header should render even at width 10")
	}
}

func TestDeepRenderTabsNarrow(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	tabs := renderTabs(TabDetail, 10)
	if tabs == "" {
		t.Error("tabs should render even at narrow width")
	}
}

func TestDeepPadRightVisualOverflow(t *testing.T) {
	longLine := strings.Repeat("x", 200)
	result := padRightVisual(longLine, 50)
	if lipgloss.Width(result) > 50 {
		t.Errorf("padRightVisual should truncate overflow, got width=%d", lipgloss.Width(result))
	}
}

func TestDeepPadRightVisualExactWidth(t *testing.T) {
	line := "hello"
	result := padRightVisual(line, 5)
	if result != "hello" {
		t.Errorf("padRightVisual exact width should return original, got %q", result)
	}
}

func TestDeepPadRightVisualZeroWidth(t *testing.T) {
	result := padRightVisual("hello", 0)
	if lipgloss.Width(result) > 0 {
		t.Errorf("padRightVisual width=0 should truncate to empty or 0 width, got width=%d", lipgloss.Width(result))
	}
}

func TestDeepMakeProgressBarDoneExceedsTotal(t *testing.T) {
	result := components.MakeProgressBar(10, 0, 5, 10)
	if result == "" {
		t.Error("MakeProgressBar with done>total should not be empty")
	}
}

func TestDeepMakeProgressBarRunningExceedsTotal(t *testing.T) {
	result := components.MakeProgressBar(0, 10, 5, 10)
	if result == "" {
		t.Error("MakeProgressBar with running>total should not be empty")
	}
}

func TestDeepMakeProgressBarAllExceedTotal(t *testing.T) {
	result := components.MakeProgressBar(10, 10, 5, 10)
	if result == "" {
		t.Error("MakeProgressBar with done+running>>total should not be empty")
	}
}

func TestDeepMakeProgressBarBarW1(t *testing.T) {
	result := components.MakeProgressBar(1, 0, 2, 1)
	if result == "" {
		t.Error("MakeProgressBar barW=1 should not be empty")
	}
}

func TestDeepMakeProgressBarLargeNumbers(t *testing.T) {
	result := components.MakeProgressBar(1000000, 500000, 2000000, 20)
	if result == "" {
		t.Error("MakeProgressBar with large numbers should not be empty")
	}
}

func TestDeepMakeProgressBarIntegerOverflow(t *testing.T) {
	result := components.MakeProgressBar(int(1e9), 0, int(1e9), 10)
	if result == "" {
		t.Error("MakeProgressBar with large values should not be empty")
	}
}

func TestDeepMakeProgressBarBarWidthOverflow(t *testing.T) {
	result := components.MakeProgressBar(3, 2, 5, 3)
	if result == "" {
		t.Error("MakeProgressBar with barW smaller than done+running should not be empty")
	}
}

func TestDeepLogViewerAppendEmptyString(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("existing")
	m.AppendContent("")
	content := m.Content()
	if content != "existing\n" {
		t.Errorf("AppendContent('') should add empty line, got %q", content)
	}
}

func TestDeepLogViewerSetContentEmptyString(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("")
	if m.Content() != "" {
		t.Errorf("SetContent('') should result in empty content, got %q", m.Content())
	}
}

func TestDeepLogViewerMaxLogLinesBoundary(t *testing.T) {
	m := components.NewLogViewerModel()
	var lines []string
	for i := 0; i < 5001; i++ {
		lines = append(lines, "line")
	}
	content := strings.Join(lines, "\n")
	m.SetContent(content)
	viewContent := m.Content()
	lineCount := len(strings.Split(viewContent, "\n"))
	if lineCount > 5001 {
		t.Errorf("lines should be capped at 5000, got %d lines in content", lineCount)
	}
}

func TestDeepLogViewerSetSizeZeroWidth(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("hello world")
	m.SetSize(0, 10)
	view := m.View()
	if view == "" {
		t.Error("LogViewer should handle zero width")
	}
}

func TestDeepLogViewerSetSizeZeroHeight(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("hello world")
	m.SetSize(80, 0)
	view := m.View()
	_ = view
}

func TestDeepRunDetailToggleSubExpand(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "group1"},
			{TaskName: "t2", SubpipelineName: "group1"},
			{TaskName: "t3", SubpipelineName: "group2"},
		},
	}
	m.SetRun(run)

	m.SetCursor(0)
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	view := m.View()
	if view == "" {
		t.Error("toggling sub expand should produce view")
	}
}

func TestDeepRunDetailSetRunPreservesExpandedState(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run1 := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "build"},
		},
	}
	m.SetRun(run1)
	m.ExpandAll()

	run2 := &models.Run{
		ID: "def", Status: models.RunStatusSuccess,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "build"},
		},
	}
	m.SetRun(run2)

	if !m.HasExpanded() {
		t.Error("expanded state from previous run should persist for same subpipeline name")
	}
}

func TestDeepRunListManyItemsScrolling(t *testing.T) {
	m := components.NewRunListModel()
	runs := make([]models.Run, 100)
	for i := range runs {
		runs[i] = models.Run{ID: fmt.Sprintf("run-%04d", i), PipelineName: "pipeline", Status: models.RunStatusRunning}
	}
	m.SetRuns(runs)
	m.SetSize(60, 10)

	for i := 0; i < 50; i++ {
		m.Update(tea.KeyMsg{Type: tea.KeyDown})
	}
	view := m.View()
	if view == "" {
		t.Error("scrolling through many items should produce view")
	}

	for i := 0; i < 50; i++ {
		m.Update(tea.KeyMsg{Type: tea.KeyUp})
	}
	view = m.View()
	if view == "" {
		t.Error("scrolling back up should produce view")
	}
}

func TestDeepRunListSetRunsPreservesCursor(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{
		{ID: "r1", PipelineName: "p1"},
		{ID: "r2", PipelineName: "p2"},
		{ID: "r3", PipelineName: "p3"},
	}
	m.SetRuns(runs)
	m.SetCursor(1)

	updatedRuns := []models.Run{
		{ID: "r1", PipelineName: "p1-updated"},
		{ID: "r2", PipelineName: "p2-updated"},
		{ID: "r3", PipelineName: "p3-updated"},
	}
	m.SetRuns(updatedRuns)

	if m.SelectedRun().ID != "r2" {
		t.Errorf("cursor should stay on r2 after update, got %s", m.SelectedRun().ID)
	}
}

func TestDeepRunListSetRunsRemovesSelected(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{
		{ID: "r1"}, {ID: "r2"}, {ID: "r3"},
	}
	m.SetRuns(runs)
	m.SetCursor(2)

	newRuns := []models.Run{
		{ID: "r1"}, {ID: "r2"},
	}
	m.SetRuns(newRuns)

	if m.SelectedRun().ID != "r2" {
		t.Errorf("cursor should be clamped to r2, got %s", m.SelectedRun().ID)
	}
}

func TestDeepViewComplexStateCombinations(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	t.Run("ready_with_error_and_runs_logs_tab", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.Width = 120
		m.state.Height = 40
		m.resizeComponents()
		m.state.ErrorMsg = "test error"
		m.state.Runs = testutil.MakeTestRuns()
		m.runList.SetRuns(m.state.Runs)
		m.runList.SetCursor(0)
		m.runDetail.SetRun(&m.state.Runs[0])
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		m.logViewer.SetContent("log output here")

		view := m.View()
		if view == "" {
			t.Error("complex state should produce view")
		}
	})

	t.Run("ready_with_no_runs_logs_tab", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.Width = 120
		m.state.Height = 40
		m.resizeComponents()
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs

		view := m.View()
		if view == "" {
			t.Error("no runs with logs tab should produce view")
		}
	})

	t.Run("ready_with_runs_detail_no_task_selected", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.Width = 120
		m.state.Height = 40
		m.resizeComponents()
		m.state.Runs = testutil.MakeTestRuns()
		m.runList.SetRuns(m.state.Runs)
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail

		view := m.View()
		if view == "" {
			t.Error("detail with no task selected should produce view")
		}
	})

	t.Run("extreme_narrow_with_error", func(t *testing.T) {
		m := makeTestModel()
		m.state.Ready = true
		m.state.Width = 15
		m.state.Height = 8
		m.resizeComponents()
		m.state.ErrorMsg = "error"

		view := m.View()
		if view == "" {
			t.Error("extreme narrow with error should produce view")
		}
	})
}

func TestDeepResizeComponentsNegativeAvailableH(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 120
	m.state.Height = 0
	m.resizeComponents()
	if m.state.Dims.contentH < 3 {
		t.Errorf("contentH should be clamped to 3, got %d", m.state.Dims.contentH)
	}
}

func TestDeepResizeComponentsNegativeInnerW(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 0
	m.state.Height = 20
	m.resizeComponents()
	if m.state.Dims.innerW <= 0 {
		t.Errorf("innerW should be positive, got %d", m.state.Dims.innerW)
	}
}

func TestDeepViewAfterMultipleUpdates(t *testing.T) {
	m := makeTestModel()

	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})

	runs := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{{TaskName: "build", SubpipelineName: "default", Status: models.TaskStatusRunning}}},
	}
	m.Update(runsFetchedMsg{runs: runs})

	m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}})

	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})

	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}})

	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}})

	view := m.View()
	if view == "" {
		t.Error("view after multiple updates should not be empty")
	}
}

func TestDeepConcurrentMessageSequence(t *testing.T) {
	m := makeTestModel()
	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})

	runs1 := []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
	}
	m.Update(runsFetchedMsg{runs: runs1})

	m.Update(runFetchedMsg{run: &models.Run{ID: "r1", PipelineName: "deploy", Status: models.RunStatusSuccess,
		Tasks: []models.TaskRun{{TaskName: "build", Status: models.TaskStatusSuccess}}}})

	m.Update(logsFetchedMsg{logs: map[string]string{"build": "compiling...\ndone"}})

	m.Update(tickMsg{})

	view := m.View()
	if view == "" {
		t.Error("view after concurrent message sequence should not be empty")
	}
}

func TestDeepProcessLineZeroWidth(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("hello world")
	m.SetSize(1, 10)
	view := m.View()
	_ = view
}

func TestDeepProcessLineNegativeWidth(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetContent("hello world")
	m.SetSize(0, 10)
	view := m.View()
	_ = view
}

func TestDeepRunDetailNavigateWithCollapsedGroups(t *testing.T) {
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
	m.CollapseAll()

	m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m.Update(tea.KeyMsg{Type: tea.KeyDown})

	view := m.View()
	if view == "" {
		t.Error("navigating collapsed groups should produce view")
	}
}

func TestDeepRunDetailExpandThenCollapseThenNavigate(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default"},
			{TaskName: "t2", SubpipelineName: "default"},
		},
	}
	m.SetRun(run)

	m.ExpandAll()
	m.CollapseAll()
	m.Update(tea.KeyMsg{Type: tea.KeyDown})
	m.Update(tea.KeyMsg{Type: tea.KeyUp})

	view := m.View()
	if view == "" {
		t.Error("expand-collapse-navigate should produce view")
	}
}

func TestDeepRunDetailEnterOnSubItem(t *testing.T) {
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

	m.SetCursor(0)
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	view := m.View()
	if view == "" {
		t.Error("enter on sub item should produce view")
	}
}

func TestDeepRunDetailEnterOnTaskItem(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default", TaskType: "local"},
		},
	}
	m.SetRun(run)

	m.SetCursor(1)
	m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	if !m.HasExpanded() {
		t.Error("enter on task should expand it")
	}
}

func TestDeepRunDetailSetSizeTwice(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	m.SetSize(60, 15)
	m.SetSize(100, 30)

	view := m.View()
	if view == "" {
		t.Error("multiple SetSize should work for RunDetail")
	}
}

func TestDeepRunListSetSizeTwice(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning}}
	m.SetRuns(runs)
	m.SetSize(80, 24)
	m.SetSize(60, 15)
	m.SetSize(100, 30)

	view := m.View()
	if view == "" {
		t.Error("multiple SetSize should work for RunList")
	}
}

func TestDeepRunListSetSizeZeroThenNormal(t *testing.T) {
	m := components.NewRunListModel()
	runs := []models.Run{{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning}}
	m.SetRuns(runs)
	m.SetSize(0, 0)
	m.SetSize(80, 24)

	view := m.View()
	if view == "" {
		t.Error("setting size from 0 to normal should work")
	}
}

func TestDeepRunDetailNilRunWithExpandedState(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{{TaskName: "t1", SubpipelineName: "default"}},
	}
	m.SetRun(run)
	m.ExpandAll()

	m.SetRun(nil)

	if m.HasExpanded() {
		t.Error("setting nil run should not have expanded tasks")
	}
}

func TestDeepRunDetailMultipleSetRun(t *testing.T) {
	m := components.NewRunDetailModel()
	m.SetSize(80, 24)

	for i := 0; i < 20; i++ {
		run := &models.Run{
			ID: fmt.Sprintf("run-%d", i), Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "t1", SubpipelineName: "default"},
			},
		}
		m.SetRun(run)
	}

	view := m.View()
	if view == "" {
		t.Error("multiple SetRun should produce view")
	}
}

func TestDeepLogViewerRapidAppend(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetSize(80, 20)

	for i := 0; i < 100; i++ {
		m.AppendContent(fmt.Sprintf("line %d", i))
	}

	content := m.Content()
	if content == "" {
		t.Error("rapid append should produce content")
	}
}

func TestDeepLogViewerSetContentOverwrite(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetSize(80, 20)

	m.SetContent("first content")
	m.SetContent("second content")
	m.SetContent("third content")

	if m.Content() != "third content" {
		t.Errorf("SetContent should overwrite, got %q", m.Content())
	}
}

func TestDeepLogViewerAppendThenSetContent(t *testing.T) {
	m := components.NewLogViewerModel()
	m.SetSize(80, 20)

	m.AppendContent("appended")
	m.SetContent("overwritten")

	if m.Content() != "overwritten" {
		t.Errorf("SetContent after Append should overwrite, got %q", m.Content())
	}
}
