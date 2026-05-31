package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/models"
)

type RunListModel struct {
	runs     []models.Run
	cursor   int
	width    int
	height   int
	viewport viewport.Model
	ready    bool
}

func NewRunListModel() RunListModel {
	return RunListModel{cursor: 0}
}

func (m *RunListModel) SetRuns(runs []models.Run) {
	prevID := ""
	if m.cursor < len(m.runs) {
		prevID = m.runs[m.cursor].ID
	}
	m.runs = runs
	if prevID != "" {
		for i, r := range runs {
			if r.ID == prevID {
				m.cursor = i
				break
			}
		}
	}
	if m.cursor >= len(m.runs) && len(m.runs) > 0 {
		m.cursor = len(m.runs) - 1
	}
	if m.ready {
		m.updateContent()
	}
}

func (m *RunListModel) SetSize(w, h int) {
	m.width = w - 1
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
	m.updateContent()
}

func (m *RunListModel) SetCursor(idx int) {
	if idx >= 0 && idx < len(m.runs) {
		m.cursor = idx
		if m.ready {
			m.updateContent()
		}
	}
}

func (m *RunListModel) SelectedRun() *models.Run {
	if len(m.runs) == 0 || m.cursor >= len(m.runs) {
		return nil
	}
	return &m.runs[m.cursor]
}

func (m RunListModel) Update(msg tea.Msg) (RunListModel, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
				m.updateContent()
				m.ensureCursorVisible()
			}
		case "down", "j":
			if m.cursor < len(m.runs)-1 {
				m.cursor++
				m.updateContent()
				m.ensureCursorVisible()
			}
		default:
			m.viewport, cmd = m.viewport.Update(msg)
		}
	default:
		m.viewport, cmd = m.viewport.Update(msg)
	}
	return m, cmd
}

func (m *RunListModel) ensureCursorVisible() {
	if !m.ready || len(m.runs) == 0 {
		return
	}
	cursorLine := m.cursor * 2
	viewTop := m.viewport.YOffset
	viewBottom := viewTop + m.viewport.Height - 1

	if cursorLine < viewTop {
		m.viewport.SetYOffset(cursorLine)
	} else if cursorLine > viewBottom {
		m.viewport.SetYOffset(cursorLine - m.viewport.Height + 1)
	}
}

func (m *RunListModel) updateContent() {
	var b strings.Builder

	if len(m.runs) == 0 {
		b.WriteString(DimStyle.Render("  (no runs)"))
		b.WriteString("\n")
	} else {
		for i, run := range m.runs {
			icon := StatusIcon(string(run.Status))
			style := StatusStyle(string(run.Status))

			isCursor := i == m.cursor
			cursorPrefix := "  "
			if isCursor {
				cursorPrefix = CursorStyle.Render("> ")
			}

			idStr := run.ID
			if len([]rune(idStr)) > 8 {
				idStr = string([]rune(idStr)[:8])
			}

			done, total := countDone(run.Tasks)
			prog := ""
			if total > 0 {
				barW := m.width / 5
				if barW < 3 {
					barW = 3
				}
				if barW > 10 {
					barW = 10
				}
				bar := MakeProgressBar(done, countRunning(run.Tasks), total, barW)
				prog = fmt.Sprintf(" %s %d/%d", bar, done, total)
			}

			line1 := fmt.Sprintf("%s%s %s %s",
				cursorPrefix,
				icon,
				style.Bold(true).Render(run.PipelineName),
				DimStyle.Render(idStr))
			b.WriteString(TruncateLine(line1, m.width))
			b.WriteString("\n")

			line2 := fmt.Sprintf("%s  %s%s",
				strings.Repeat(" ", lipgloss.Width(cursorPrefix)),
				LabelStyle.Render(FormatTime(run.StartedAt)),
				prog)
			b.WriteString(TruncateLine(line2, m.width))
			b.WriteString("\n")
		}
	}

	m.viewport.SetContent(b.String())
	m.ensureCursorVisible()
}

func (m RunListModel) View() string {
	if m.ready {
		return m.viewport.View()
	}
	return DimStyle.Render("  (no runs)")
}

func countDone(tasks []models.TaskRun) (int, int) {
	done := 0
	for _, t := range tasks {
		if t.Status == "success" || t.Status == "failed" || t.Status == "skipped" || t.Status == "cancelled" {
			done++
		}
	}
	return done, len(tasks)
}

func countRunning(tasks []models.TaskRun) int {
	n := 0
	for _, t := range tasks {
		if t.Status == "running" {
			n++
		}
	}
	return n
}
