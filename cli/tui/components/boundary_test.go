package components

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
	"github.com/taskpps/ppsctl/models"
	testutil "github.com/taskpps/ppsctl/tui/testutil"
)

func TestRunListBoundaryEmptyList(t *testing.T) {
	m := NewRunListModel()
	m.SetSize(60, 10)
	view := m.View()
	if !strings.Contains(view, "(no runs)") {
		t.Errorf("empty list should show (no runs), got: %s", view)
	}
}

func TestRunListBoundaryAllStatusIcons(t *testing.T) {
	m := NewRunListModel()
	runs := []models.Run{
		{ID: "r1abcdefg", PipelineName: "p1", Status: models.RunStatusPending},
		{ID: "r2abcdefg", PipelineName: "p2", Status: models.RunStatusRunning},
		{ID: "r3abcdefg", PipelineName: "p3", Status: models.RunStatusSuccess},
		{ID: "r4abcdefg", PipelineName: "p4", Status: models.RunStatusFailed},
		{ID: "r5abcdefg", PipelineName: "p5", Status: models.RunStatusCancelled},
	}
	m.SetRuns(runs)
	m.SetSize(60, 20)
	view := m.View()

	expectedIcons := []string{"○", "▶", "✔", "✘", "✕"}
	for _, icon := range expectedIcons {
		if !strings.Contains(view, icon) {
			t.Errorf("view should contain status icon %q", icon)
		}
	}
}

func TestRunListBoundaryCursorUpAtZero(t *testing.T) {
	m := NewRunListModel()
	m.runs = []models.Run{{ID: "1"}, {ID: "2"}}
	m.SetSize(60, 10)
	m.cursor = 0

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyUp})
	if m2.cursor != 0 {
		t.Errorf("cursor should stay at 0, got %d", m2.cursor)
	}
}

func TestRunListBoundaryCursorDownAtLast(t *testing.T) {
	m := NewRunListModel()
	m.runs = []models.Run{{ID: "1"}, {ID: "2"}}
	m.SetSize(60, 10)
	m.cursor = 1

	m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyDown})
	if m2.cursor != 1 {
		t.Errorf("cursor should stay at last index, got %d", m2.cursor)
	}
}

func TestRunListBoundaryCursorOverflowAdjust(t *testing.T) {
	m := NewRunListModel()
	m.cursor = 5
	runs := []models.Run{{ID: "1"}, {ID: "2"}}
	m.SetRuns(runs)
	if m.cursor != 1 {
		t.Errorf("cursor should be adjusted to last index, got %d", m.cursor)
	}
}

func TestRunListBoundaryInvalidSetCursor(t *testing.T) {
	m := NewRunListModel()
	m.runs = []models.Run{{ID: "1"}, {ID: "2"}}
	m.SetCursor(0)

	m.SetCursor(-1)
	if m.cursor != 0 {
		t.Errorf("cursor should not change for -1, got %d", m.cursor)
	}

	m.SetCursor(1000)
	if m.cursor != 0 {
		t.Errorf("cursor should not change for 1000, got %d", m.cursor)
	}
}

func TestRunListBoundarySelectedRunEmpty(t *testing.T) {
	m := NewRunListModel()
	if m.SelectedRun() != nil {
		t.Error("SelectedRun should return nil for empty list")
	}
}

func TestRunListBoundaryNarrowWidthTruncation(t *testing.T) {
	m := NewRunListModel()
	runs := []models.Run{
		{ID: "verylongrunid1234567890", PipelineName: "very-long-pipeline-name", Status: models.RunStatusRunning},
	}
	m.SetRuns(runs)
	m.SetSize(20, 10)
	view := m.View()
	if view == "" {
		t.Error("view should handle narrow width truncation")
	}
}

func TestRunDetailBoundaryNilRun(t *testing.T) {
	m := NewRunDetailModel()
	m.SetSize(80, 24)
	m.SetRun(nil)
	view := m.View()
	if !strings.Contains(view, "select a run") {
		t.Errorf("nil run should show hint, got: %s", view)
	}
}

func TestRunDetailBoundaryEmptyTasks(t *testing.T) {
	m := NewRunDetailModel()
	m.SetSize(80, 24)
	m.SetRun(&models.Run{ID: "abc", Status: models.RunStatusRunning, Tasks: []models.TaskRun{}})
	view := m.View()
	if !strings.Contains(view, "no tasks") {
		t.Errorf("empty tasks should show hint, got: %s", view)
	}
}

func TestRunDetailBoundaryExpandCollapseAll(t *testing.T) {
	m := NewRunDetailModel()
	m.SetSize(80, 24)
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", SubpipelineName: "default"},
			{TaskName: "t2", SubpipelineName: "default"},
		},
	}
	m.SetRun(run)

	if m.HasExpanded() {
		t.Error("should start with no expanded tasks")
	}

	m.ExpandAll()
	if !m.HasExpanded() {
		t.Error("ExpandAll should expand all tasks")
	}

	m.CollapseAll()
	if m.HasExpanded() {
		t.Error("CollapseAll should collapse all tasks")
	}
}

func TestRunDetailBoundaryCursorOverflow(t *testing.T) {
	m := NewRunDetailModel()
	m.cursor = 10
	run := &models.Run{
		Tasks: []models.TaskRun{{TaskName: "t1", SubpipelineName: "default"}, {TaskName: "t2", SubpipelineName: "default"}},
	}
	m.SetRun(run)
	if m.cursor > 3 {
		t.Errorf("cursor should be adjusted, got %d", m.cursor)
	}
}

func TestRunDetailBoundaryExpandedTaskWithTimestamps(t *testing.T) {
	m := NewRunDetailModel()
	m.SetSize(80, 24)
	started := "2024-01-15T10:30:00Z"
	finished := "2024-01-15T11:45:00Z"
	m.expanded[0] = true
	run := &models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "build", SubpipelineName: "default", TaskType: "local", Status: models.TaskStatusSuccess, StartedAt: &started, FinishedAt: &finished},
		},
	}
	m.SetRun(run)
	view := m.View()
	if !strings.Contains(view, "start:") {
		t.Errorf("expanded task should show start time, got: %s", view)
	}
	if !strings.Contains(view, "end:") {
		t.Errorf("expanded task with FinishedAt should show end time, got: %s", view)
	}
}

func TestLogViewerBoundaryEmptyContent(t *testing.T) {
	m := NewLogViewerModel()
	view := m.View()
	if !strings.Contains(view, "(no output)") {
		t.Errorf("empty viewer should show (no output), got: %s", view)
	}
}

func TestLogViewerBoundaryShortContent(t *testing.T) {
	m := NewLogViewerModel()
	m.SetContent("hello")
	m.SetSize(80, 10)
	view := m.View()
	if !strings.Contains(view, "hello") {
		t.Errorf("viewer should show content, got: %s", view)
	}
}

func TestLogViewerBoundaryLongContent(t *testing.T) {
	m := NewLogViewerModel()
	longContent := testutil.MakeLongLogContent(5000)
	m.SetContent(longContent)
	m.SetSize(80, 20)
	view := m.View()
	if view == "" {
		t.Error("viewer should handle long content")
	}
	if len(m.lines) > 5000+100 {
		t.Errorf("lines should be capped, got %d", len(m.lines))
	}
}

func TestLogViewerBoundaryAppendContent(t *testing.T) {
	m := NewLogViewerModel()
	m.AppendContent("a")
	m.AppendContent("b")
	if m.Content() != "a\nb" {
		t.Errorf("append should add newline between, got %q", m.Content())
	}
}

func TestLogViewerBoundaryPageScrolling(t *testing.T) {
	m := NewLogViewerModel()
	var content string
	for i := 0; i < 30; i++ {
		content += "line " + strings.Repeat("x", 20) + "\n"
	}
	m.SetContent(content)
	m.SetSize(80, 10)

	m.Update(tea.KeyMsg{Type: tea.KeyPgDown})
	m.Update(tea.KeyMsg{Type: tea.KeyPgDown})
	m.Update(tea.KeyMsg{Type: tea.KeyPgUp})
	m.Update(tea.KeyMsg{Type: tea.KeyHome})
	m.Update(tea.KeyMsg{Type: tea.KeyEnd})

	view := m.View()
	if view == "" {
		t.Error("viewer should handle page scrolling")
	}
}

func TestLogViewerBoundaryNonKeyMessage(t *testing.T) {
	m := NewLogViewerModel()
	m.SetContent("original content")
	m.SetSize(80, 10)
	contentBefore := m.Content()

	m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
	if m.Content() != contentBefore {
		t.Error("WindowSizeMsg should not change content")
	}
}

func TestLogViewerBoundarySetSizeSetsReady(t *testing.T) {
	m := NewLogViewerModel()
	if m.ready {
		t.Error("should not be ready initially")
	}
	m.SetSize(80, 20)
	if !m.ready {
		t.Error("SetSize should set ready to true")
	}
}

func TestStylesBoundaryTruncateLineSmallWidth(t *testing.T) {
	result := TruncateLine("abc", 1)
	if result != "" {
		t.Errorf("TruncateLine with width 1 should return empty, got %q", result)
	}
}

func TestStylesBoundaryTruncateLineNegativeWidth(t *testing.T) {
	result := TruncateLine("hello", -5)
	if result != "" {
		t.Errorf("TruncateLine with negative width should return empty, got %q", result)
	}
}

func TestStylesBoundaryTruncateLineExactWidth(t *testing.T) {
	result := TruncateLine("hello", 5)
	if result != "hello" {
		t.Errorf("TruncateLine with exact width should return original, got %q", result)
	}
}

func TestStylesBoundaryMakeProgressBarAllDone(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	result := MakeProgressBar(5, 0, 5, 5)
	if result == "" {
		t.Error("progress bar should not be empty")
	}
	stripped := stripANSI(result)
	if !strings.Contains(stripped, "█████") {
		t.Errorf("all done should show full bar, got: %s", stripped)
	}
}

func TestStylesBoundaryMakeProgressBarMixed(t *testing.T) {
	lipgloss.SetColorProfile(termenv.Ascii)
	defer lipgloss.SetColorProfile(termenv.TrueColor)

	result := MakeProgressBar(3, 1, 5, 5)
	if result == "" {
		t.Error("progress bar should not be empty")
	}
	stripped := stripANSI(result)
	if !strings.Contains(stripped, "█") {
		t.Errorf("mixed progress should show some done blocks, got: %s", stripped)
	}
	if !strings.Contains(stripped, "▓") {
		t.Errorf("mixed progress should show running block, got: %s", stripped)
	}
	if !strings.Contains(stripped, "░") {
		t.Errorf("mixed progress should show todo blocks, got: %s", stripped)
	}
}

func TestStylesBoundaryMakeProgressBarZeroTotal(t *testing.T) {
	result := MakeProgressBar(0, 0, 0, 5)
	if result != "" {
		t.Errorf("zero total should return empty, got %q", result)
	}
}

func TestStylesBoundaryMakeProgressBarZeroBarW(t *testing.T) {
	result := MakeProgressBar(3, 1, 5, 0)
	if result != "" {
		t.Errorf("zero barW should return empty, got %q", result)
	}
}

func TestStylesBoundaryFormatTimeExactFormat(t *testing.T) {
	s := "2024-01-15T10:30:00Z"
	result := FormatTime(&s)
	if result != "01-15T10:30:00" {
		t.Errorf("FormatTime = %q, want %q", result, "01-15T10:30:00")
	}
}

func TestStylesBoundaryFormatTimeShort(t *testing.T) {
	s := "short"
	result := FormatTime(&s)
	if result != "short" {
		t.Errorf("FormatTime short string = %q, want %q", result, "short")
	}
}

func TestStylesBoundaryStatusIconPartial(t *testing.T) {
	result := StatusIcon("partial")
	if result != "◐" {
		t.Errorf("StatusIcon(partial) = %q, want %q", result, "◐")
	}
}

func stripANSI(s string) string {
	var result strings.Builder
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
		result.WriteRune(r)
	}
	return result.String()
}
