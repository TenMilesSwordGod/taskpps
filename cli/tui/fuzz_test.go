package tui

import (
	"fmt"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

func FuzzModelUpdate(f *testing.F) {
	f.Add("q")
	f.Add("j")
	f.Add("k")
	f.Add("enter")
	f.Add("p")
	f.Add("n")
	f.Add("t")
	f.Add("c")
	f.Add("r")
	f.Add("b")
	f.Add("\x00")
	f.Add(strings.Repeat("a", 1000))

	f.Fuzz(func(t *testing.T, input string) {
		m := makeTestModel()
		m.ready = true
		m.width = 120
		m.height = 40
		m.resizeComponents()

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(input)}
		newM, _ := m.Update(msg)
		_ = newM.(Model).View()
	})
}

func FuzzTruncateLine(f *testing.F) {
	f.Add("hello", 10)
	f.Add("hello world", 5)
	f.Add("hello", 0)
	f.Add("hello", -1)
	f.Add("", 10)
	f.Add("▶ ✔ ✘ ○", 6)
	f.Add(strings.Repeat("x", 500), 20)
	f.Add("hello", 1)
	f.Add("hello", 2)
	f.Add("hello", 3)
	f.Add("hello", 4)
	f.Add("你好世界", 5)
	f.Add("██████████", 5)

	f.Fuzz(func(t *testing.T, line string, width int) {
		result := components.TruncateLine(line, width)
		_ = result
	})
}

func FuzzMakeProgressBar(f *testing.F) {
	f.Add(3, 1, 5, 10)
	f.Add(0, 0, 0, 5)
	f.Add(-1, -1, -1, -1)
	f.Add(5, 0, 3, 10)
	f.Add(0, 0, 5, 0)
	f.Add(10, 0, 5, 10)
	f.Add(0, 10, 5, 10)
	f.Add(10, 10, 5, 10)
	f.Add(1, 0, 2, 1)
	f.Add(1000000, 500000, 2000000, 20)

	f.Fuzz(func(t *testing.T, done, running, total, barW int) {
		result := components.MakeProgressBar(done, running, total, barW)
		_ = result
	})
}

func FuzzFormatTime(f *testing.F) {
	f.Add("")
	f.Add("2024-01-15T10:30:00Z")
	f.Add("short")
	f.Add(strings.Repeat("x", 100))
	f.Add("X")
	f.Add("2024-01-15T10:30:00")
	f.Add("2024-01-15T10:30:0")

	f.Fuzz(func(t *testing.T, timeStr string) {
		result := components.FormatTime(&timeStr)
		_ = result
	})
}

func FuzzFormatTimeNil(f *testing.F) {
	f.Fuzz(func(t *testing.T, _ string) {
		result := components.FormatTime(nil)
		if result != "-" {
			t.Errorf("FormatTime(nil) = %q, want %q", result, "-")
		}
	})
}

func FuzzStatusIcon(f *testing.F) {
	f.Add("running")
	f.Add("pending")
	f.Add("success")
	f.Add("failed")
	f.Add("skipped")
	f.Add("cancelled")
	f.Add("unknown")
	f.Add("")
	f.Add(strings.Repeat("x", 100))
	f.Add("partial")

	f.Fuzz(func(t *testing.T, status string) {
		result := components.StatusIcon(status)
		_ = result
	})
}

func FuzzMergeRuns(f *testing.F) {
	f.Add("", "", 0, 0)
	f.Add("r1", "r1", 1, 1)
	f.Add("r1", "r2", 1, 1)
	f.Add("r1", "r1", 5, 5)
	f.Add("", "", 50, 50)

	f.Fuzz(func(t *testing.T, id1, id2 string, count1, count2 int) {
		if count1 < 0 {
			count1 = 0
		}
		if count2 < 0 {
			count2 = 0
		}
		if count1 > 50 {
			count1 = 50
		}
		if count2 > 50 {
			count2 = 50
		}

		existing := make([]models.Run, count1)
		for i := range existing {
			existing[i] = models.Run{ID: id1}
		}

		newRuns := make([]models.Run, count2)
		for i := range newRuns {
			newRuns[i] = models.Run{ID: id2}
		}

		result := mergeRuns(existing, newRuns)
		_ = result
	})
}

func FuzzModelUpdateWithRuns(f *testing.F) {
	f.Add("j")
	f.Add("k")
	f.Add("down")
	f.Add("up")
	f.Add("q")
	f.Add("enter")
	f.Add("tab")
	f.Add("t")
	f.Add("c")
	f.Add("b")
	f.Add("p")
	f.Add("n")
	f.Add("r")
	f.Add("\x00")

	f.Fuzz(func(t *testing.T, input string) {
		m := makeTestModel()
		m.ready = true
		m.width = 120
		m.height = 40
		m.resizeComponents()

		runs := []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
			{ID: "r3", PipelineName: "test", Status: models.RunStatusFailed},
		}
		m.runs = runs
		m.runList.SetRuns(runs)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(input)}
		newM, _ := m.Update(msg)
		_ = newM.(Model).View()
	})
}

func FuzzModelUpdateWithSmallWindow(f *testing.F) {
	f.Add("j", 10, 5)
	f.Add("q", 80, 24)
	f.Add("enter", 20, 8)
	f.Add("k", 0, 0)
	f.Add("r", 42, 10)
	f.Add("t", 120, 40)

	f.Fuzz(func(t *testing.T, input string, width, height int) {
		if width < 0 {
			width = 0
		}
		if height < 0 {
			height = 0
		}
		if width > 300 {
			width = 300
		}
		if height > 100 {
			height = 100
		}

		m := makeTestModel()
		m.ready = true
		m.width = width
		m.height = height
		m.resizeComponents()

		runs := []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		}
		m.runs = runs
		m.runList.SetRuns(runs)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(input)}
		newM, _ := m.Update(msg)
		_ = newM.(Model).View()
	})
}

func FuzzModelUpdateWithLongData(f *testing.F) {
	f.Add("j", "verylongid12345678901234567890", "pipeline-name-that-is-very-long")
	f.Add("k", "a", "")
	f.Add("enter", strings.Repeat("x", 200), strings.Repeat("Y", 200))

	f.Fuzz(func(t *testing.T, input, runID, pipelineName string) {
		if len(runID) > 300 {
			runID = runID[:300]
		}
		if len(pipelineName) > 300 {
			pipelineName = pipelineName[:300]
		}

		m := makeTestModel()
		m.ready = true
		m.width = 120
		m.height = 40
		m.resizeComponents()

		runs := []models.Run{
			{ID: runID, PipelineName: pipelineName, Status: models.RunStatusRunning},
		}
		m.runs = runs
		m.runList.SetRuns(runs)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(input)}
		newM, _ := m.Update(msg)
		_ = newM.(Model).View()
	})
}

func FuzzRunListUpdate(f *testing.F) {
	f.Add("up", 3)
	f.Add("down", 3)
	f.Add("j", 0)
	f.Add("k", 100)

	f.Fuzz(func(t *testing.T, key string, runCount int) {
		if runCount < 0 {
			runCount = 0
		}
		if runCount > 200 {
			runCount = 200
		}

		m := components.NewRunListModel()
		runs := make([]models.Run, runCount)
		for i := range runs {
			runs[i] = models.Run{
				ID:           fmt.Sprintf("run-%04d", i),
				PipelineName: fmt.Sprintf("pipeline-%d", i),
				Status:       models.RunStatusRunning,
			}
		}
		m.SetRuns(runs)
		m.SetSize(60, 10)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(key)}
		newM, _ := m.Update(msg)
		_ = newM.View()
	})
}

func FuzzRunDetailUpdate(f *testing.F) {
	f.Add("up", 3)
	f.Add("down", 3)
	f.Add("enter", 5)
	f.Add("j", 0)
	f.Add("k", 50)

	f.Fuzz(func(t *testing.T, key string, taskCount int) {
		if taskCount < 0 {
			taskCount = 0
		}
		if taskCount > 100 {
			taskCount = 100
		}

		m := components.NewRunDetailModel()
		tasks := make([]models.TaskRun, taskCount)
		for i := range tasks {
			statuses := []models.TaskStatus{models.TaskStatusPending, models.TaskStatusRunning, models.TaskStatusSuccess, models.TaskStatusFailed, models.TaskStatusSkipped, models.TaskStatusCancelled}
			tasks[i] = models.TaskRun{
				TaskName:        fmt.Sprintf("task-%d", i),
				SubpipelineName: "default",
				Status:          statuses[i%len(statuses)],
			}
		}
		run := &models.Run{
			ID:     "test-run",
			Status: models.RunStatusRunning,
			Tasks:  tasks,
		}
		m.SetRun(run)
		m.SetSize(80, 24)

		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(key)}
		m.Update(msg)
		_ = m.View()
	})
}

func FuzzLogViewerContent(f *testing.F) {
	f.Add("hello world", 80, 20)
	f.Add(strings.Repeat("A", 1000), 80, 20)
	f.Add("line1\nline2\nline3", 40, 10)
	f.Add("", 0, 0)
	f.Add("test", 1, 1)

	f.Fuzz(func(t *testing.T, content string, width, height int) {
		if width < 0 {
			width = 0
		}
		if height < 0 {
			height = 0
		}
		if width > 300 {
			width = 300
		}
		if height > 100 {
			height = 100
		}

		m := components.NewLogViewerModel()
		m.SetContent(content)
		m.SetSize(width, height)
		_ = m.View()

		m.AppendContent("appended")
		_ = m.View()
	})
}

func FuzzModelViewWithResize(f *testing.F) {
	f.Add(120, 40, 80, 24)
	f.Add(10, 5, 240, 60)
	f.Add(0, 0, 120, 40)
	f.Add(42, 10, 80, 24)
	f.Add(1, 1, 300, 100)

	f.Fuzz(func(t *testing.T, w1, h1, w2, h2 int) {
		if w1 < 0 {
			w1 = 0
		}
		if h1 < 0 {
			h1 = 0
		}
		if w2 < 0 {
			w2 = 0
		}
		if h2 < 0 {
			h2 = 0
		}
		if w1 > 500 {
			w1 = 500
		}
		if h1 > 200 {
			h1 = 200
		}
		if w2 > 500 {
			w2 = 500
		}
		if h2 > 200 {
			h2 = 200
		}

		m := makeTestModel()
		m.Update(tea.WindowSizeMsg{Width: w1, Height: h1})
		m.Update(runsFetchedMsg{runs: []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		}})
		_ = m.View()

		m.Update(tea.WindowSizeMsg{Width: w2, Height: h2})
		_ = m.View()
	})
}

func FuzzTruncateStr(f *testing.F) {
	f.Add("hello world", 5)
	f.Add("hello", 5)
	f.Add("", 10)
	f.Add("test", 0)
	f.Add("test", 1)
	f.Add("test", 3)
	f.Add("test", 4)
	f.Add(strings.Repeat("x", 200), 20)
	f.Add("你好世界测试", 4)

	f.Fuzz(func(t *testing.T, s string, maxLen int) {
		result := truncateStr(s, maxLen)
		_ = result
	})
}

func FuzzPadRightVisual(f *testing.F) {
	f.Add("hello", 10)
	f.Add("hello", 5)
	f.Add("hello", 0)
	f.Add("hello", -1)
	f.Add(strings.Repeat("x", 200), 50)
	f.Add("", 10)

	f.Fuzz(func(t *testing.T, line string, width int) {
		result := padRightVisual(line, width)
		_ = result
	})
}
