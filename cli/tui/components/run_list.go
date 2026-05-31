package components

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/models"
)

var (
	DimStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("#666666"))
	LabelStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("#888888"))
	BadgeStyle    = lipgloss.NewStyle().Padding(0, 1)
	ProgressDone  = "█"
	ProgressTodo  = "░"
)

func formatTime(t *string) string {
	if t == nil {
		return "-"
	}
	s := *t
	if len(s) >= 19 {
		return s[:19]
	}
	return s
}

func taskProgress(tasks []models.TaskRun) string {
	done := 0
	for _, t := range tasks {
		if t.Status == "success" || t.Status == "failed" || t.Status == "skipped" || t.Status == "cancelled" {
			done++
		}
	}
	total := len(tasks)
	if total == 0 {
		return ""
	}

	barW := 8
	doneW := barW * done / total
	if doneW > barW {
		doneW = barW
	}
	todoW := barW - doneW

	bar := StatusSuccessStyle.Render(strings.Repeat(ProgressDone, doneW)) +
		DimStyle.Render(strings.Repeat(ProgressTodo, todoW))

	return fmt.Sprintf("%s %d/%d", bar, done, total)
}

type RunListModel struct {
	runs   []models.Run
	cursor int
	width  int
	height int
}

func NewRunListModel() RunListModel {
	return RunListModel{cursor: 0}
}

func (m *RunListModel) SetRuns(runs []models.Run) {
	m.runs = runs
	if m.cursor >= len(m.runs) && len(m.runs) > 0 {
		m.cursor = len(m.runs) - 1
	}
}

func (m *RunListModel) SetSize(w, h int) {
	m.width = w
	m.height = h
}

func (m *RunListModel) SetCursor(idx int) {
	if idx >= 0 && idx < len(m.runs) {
		m.cursor = idx
	}
}

func (m *RunListModel) SelectedRun() *models.Run {
	if len(m.runs) == 0 || m.cursor >= len(m.runs) {
		return nil
	}
	return &m.runs[m.cursor]
}

func (m RunListModel) Update(msg tea.Msg) (RunListModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.runs)-1 {
				m.cursor++
			}
		}
	}
	return m, nil
}

func (m RunListModel) View() string {
	var b strings.Builder

	if len(m.runs) == 0 {
		b.WriteString("\n")
		b.WriteString(DimStyle.Render("  (no runs)"))
		b.WriteString("\n")
		return b.String()
	}

	visible := m.height / 2
	if visible < 1 {
		visible = 1
	}
	if visible > len(m.runs) {
		visible = len(m.runs)
	}

	start := m.cursor - visible/2
	if start < 0 {
		start = 0
	}
	end := start + visible
	if end > len(m.runs) {
		end = len(m.runs)
		start = end - visible
		if start < 0 {
			start = 0
		}
	}

	renderedLines := 0
	for i := start; i < end && renderedLines < m.height-1; i++ {
		run := m.runs[i]
		icon := StatusIcon(string(run.Status))
		style := StatusStyle(string(run.Status))

		isCursor := i == m.cursor
		cursorPrefix := "  "
		if isCursor {
			cursorPrefix = CursorStyle.Render("> ")
		}

		idStr := run.ID
		if len(idStr) > 8 {
			idStr = idStr[:8]
		}

		line1 := fmt.Sprintf("%s%s %s %s",
			cursorPrefix,
			icon,
			style.Bold(true).Render(run.PipelineName),
			LabelStyle.Render(idStr))
		line1 = TruncateLine(line1, m.width)

		timeStr := formatTime(run.StartedAt)
		prog := taskProgress(run.Tasks)
		line2 := fmt.Sprintf("%s  %s  %s",
			strings.Repeat(" ", lipgloss.Width(cursorPrefix)+2),
			LabelStyle.Render(timeStr),
			prog)
		line2 = TruncateLine(line2, m.width)

		b.WriteString(line1)
		b.WriteString("\n")
		b.WriteString(line2)
		b.WriteString("\n")
		renderedLines += 2
	}

	for renderedLines < m.height-1 {
		b.WriteString("\n")
		renderedLines++
	}

	return b.String()
}
