package components

import (
	"fmt"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/models"
)

type RunDetailModel struct {
	run      *models.Run
	cursor   int
	expanded map[int]bool
	width    int
	height   int
}

func NewRunDetailModel() RunDetailModel {
	return RunDetailModel{
		expanded: make(map[int]bool),
	}
}

func (m *RunDetailModel) SetRun(run *models.Run) {
	m.run = run
	if run != nil && m.cursor >= len(run.Tasks) && len(run.Tasks) > 0 {
		m.cursor = len(run.Tasks) - 1
	}
}

func (m *RunDetailModel) SetSize(w, h int) {
	m.width = w
	m.height = h
}

func (m *RunDetailModel) SelectedRun() *models.Run {
	return m.run
}

func (m *RunDetailModel) SelectedTask() *models.TaskRun {
	if m.run == nil || len(m.run.Tasks) == 0 || m.cursor >= len(m.run.Tasks) {
		return nil
	}
	return &m.run.Tasks[m.cursor]
}

func (m RunDetailModel) Update(msg tea.Msg) (RunDetailModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.run != nil && m.cursor < len(m.run.Tasks)-1 {
				m.cursor++
			}
		case "enter":
			if m.run != nil && len(m.run.Tasks) > 0 {
				m.expanded[m.cursor] = !m.expanded[m.cursor]
			}
		}
	}
	return m, nil
}

func (m RunDetailModel) View() string {
	var b strings.Builder

	title := TitleStyle.Render("Run Detail")
	b.WriteString(title)
	b.WriteString("\n\n")

	if m.run == nil {
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(select a run)"))
		return b.String()
	}

	b.WriteString(fmt.Sprintf("ID: %s\n", m.run.ID))
	b.WriteString(fmt.Sprintf("Pipeline: %s\n", m.run.PipelineName))

	statusStyle := StatusStyle(string(m.run.Status))
	b.WriteString(fmt.Sprintf("Status: %s\n", statusStyle.Render(string(m.run.Status))))

	if m.run.StartedAt != nil {
		b.WriteString(fmt.Sprintf("Started: %s\n", *m.run.StartedAt))
	}
	if m.run.FinishedAt != nil {
		b.WriteString(fmt.Sprintf("Finished: %s\n", *m.run.FinishedAt))
	}
	b.WriteString("\n")
	b.WriteString(TitleStyle.Render("Tasks"))
	b.WriteString("\n")

	if len(m.run.Tasks) == 0 {
		b.WriteString("  (no tasks)\n")
	} else {
		for i, task := range m.run.Tasks {
			icon := StatusIcon(string(task.Status))
			style := StatusStyle(string(task.Status))

			expandIcon := "  "
			if m.expanded[i] {
				expandIcon = "▼ "
			}

			line := fmt.Sprintf("%s%s %s  %s", expandIcon, icon, task.TaskName, style.Render(string(task.Status)))
			if task.ExitCode != nil {
				line += fmt.Sprintf(" (exit: %d)", *task.ExitCode)
			}

			if i == m.cursor {
				line = CursorStyle.Render(">") + line[1:]
			}

			b.WriteString(line)
			b.WriteString("\n")

			if m.expanded[i] {
				b.WriteString(fmt.Sprintf("    Type: %s\n", task.TaskType))
				if task.StartedAt != nil {
					b.WriteString(fmt.Sprintf("    Started: %s\n", *task.StartedAt))
				}
				if task.FinishedAt != nil {
					b.WriteString(fmt.Sprintf("    Finished: %s\n", *task.FinishedAt))
				}
				b.WriteString("\n")
			}
		}
	}

	return b.String()
}