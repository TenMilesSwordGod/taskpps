package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
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
	viewport viewport.Model
	ready    bool
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
	if m.ready {
		m.updateViewportContent()
	}
}

func (m *RunDetailModel) SetSize(w, h int) {
	m.width = w
	m.height = h
	if !m.ready {
		m.viewport = viewport.New(w, h)
		m.viewport.YPosition = 0
		m.viewport.Style = lipgloss.NewStyle()
		m.ready = true
	} else {
		m.viewport.Width = w
		m.viewport.Height = h
	}
	m.updateViewportContent()
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

func (m *RunDetailModel) Update(msg tea.Msg) tea.Cmd {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
				m.updateViewportContent()
			} else {
				m.viewport, cmd = m.viewport.Update(msg)
			}
		case "down", "j":
			if m.run != nil && m.cursor < len(m.run.Tasks)-1 {
				m.cursor++
				m.updateViewportContent()
			} else {
				m.viewport, cmd = m.viewport.Update(msg)
			}
		case "enter":
			if m.run != nil && len(m.run.Tasks) > 0 {
				m.expanded[m.cursor] = !m.expanded[m.cursor]
				m.updateViewportContent()
			}
		default:
			m.viewport, cmd = m.viewport.Update(msg)
		}
	default:
		m.viewport, cmd = m.viewport.Update(msg)
	}
	return cmd
}

func (m *RunDetailModel) updateViewportContent() {
	var b strings.Builder

	if m.run == nil {
		b.WriteString("\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(select a run)"))
		b.WriteString("\n")
	} else {
		// Helper to truncate lines
		truncateLine := func(line string) string {
			if m.width > 0 && lipgloss.Width(line) > m.width {
				for lipgloss.Width(line) > m.width-3 && len(line) > 3 {
					line = line[:len(line)-1]
				}
				line = line + "..."
			}
			return line
		}

		b.WriteString(truncateLine(fmt.Sprintf("ID: %s", m.run.ID)))
		b.WriteString("\n")
		b.WriteString(truncateLine(fmt.Sprintf("Pipeline: %s", m.run.PipelineName)))
		b.WriteString("\n")

		statusStyle := StatusStyle(string(m.run.Status))
		b.WriteString(truncateLine(fmt.Sprintf("Status: %s", statusStyle.Render(string(m.run.Status)))))
		b.WriteString("\n")

		if m.run.StartedAt != nil {
			b.WriteString(truncateLine(fmt.Sprintf("Started: %s", *m.run.StartedAt)))
			b.WriteString("\n")
		}
		if m.run.FinishedAt != nil {
			b.WriteString(truncateLine(fmt.Sprintf("Finished: %s", *m.run.FinishedAt)))
			b.WriteString("\n")
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

				b.WriteString(truncateLine(line))
				b.WriteString("\n")

				if m.expanded[i] {
					b.WriteString(truncateLine(fmt.Sprintf("    Type: %s", task.TaskType)))
					b.WriteString("\n")
					if task.StartedAt != nil {
						b.WriteString(truncateLine(fmt.Sprintf("    Started: %s", *task.StartedAt)))
						b.WriteString("\n")
					}
					if task.FinishedAt != nil {
						b.WriteString(truncateLine(fmt.Sprintf("    Finished: %s", *task.FinishedAt)))
						b.WriteString("\n")
					}
					b.WriteString("\n")
				}
			}
		}
	}

	m.viewport.SetContent(b.String())
}

func (m RunDetailModel) View() string {
	if m.ready {
		return m.viewport.View()
	}
	var b strings.Builder
	if m.run == nil {
		b.WriteString("\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(select a run)"))
		b.WriteString("\n")
	}
	return b.String()
}