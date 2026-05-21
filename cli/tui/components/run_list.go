package components

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/models"
)

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

	title := TitleStyle.Render("Runs")
	b.WriteString(title)
	b.WriteString("\n\n")

	if len(m.runs) == 0 {
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(no runs)"))
		return b.String()
	}

	visible := m.height - 4
	if visible < 1 {
		visible = 1
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

	for i := start; i < end; i++ {
		run := m.runs[i]
		icon := StatusIcon(string(run.Status))
		style := StatusStyle(string(run.Status))

		line := fmt.Sprintf("%s %s  %s", icon, run.ID[:min(8, len(run.ID))], run.PipelineName)

		if i == m.cursor {
			line = CursorStyle.Render("> ") + style.Render(line)
		} else {
			line = "  " + style.Render(line)
		}

		if m.width > 0 && len(line) > m.width {
			line = line[:m.width-1]
		}
		b.WriteString(line)
		b.WriteString("\n")
	}

	return b.String()
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}