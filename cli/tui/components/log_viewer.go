package components

import (
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

const maxLogLines = 5000

type LogViewerModel struct {
	viewport viewport.Model
	lines    []string
	ready    bool
	width    int
	loading  bool
}

func NewLogViewerModel() LogViewerModel {
	return LogViewerModel{}
}

func processLine(line string, width int) string {
	if width <= 0 {
		return ""
	}
	return TruncateLine(line, width)
}

func processLines(lines []string, width int) []string {
	processed := make([]string, len(lines))
	for i, line := range lines {
		processed[i] = processLine(line, width)
	}
	return processed
}

func (m *LogViewerModel) SetSize(w, h int) {
	m.width = w - 1
	if m.width < 0 {
		m.width = 0
	}
	if !m.ready {
		m.viewport = viewport.New(w, h)
		m.viewport.YPosition = 0
		m.viewport.Style = lipgloss.NewStyle()
		m.ready = true
	} else {
		m.viewport.Width = w
		m.viewport.Height = h
	}
	processedLines := processLines(m.lines, w)
	m.viewport.SetContent(strings.Join(processedLines, "\n"))
	m.viewport.GotoBottom()
}

func (m *LogViewerModel) SetContent(content string) {
	m.lines = strings.Split(content, "\n")
	if len(m.lines) == 1 && m.lines[0] == "" {
		m.lines = nil
	}
	if len(m.lines) > maxLogLines {
		m.lines = m.lines[len(m.lines)-maxLogLines:]
	}
	if m.ready {
		processedLines := processLines(m.lines, m.width)
		m.viewport.SetContent(strings.Join(processedLines, "\n"))
		m.viewport.GotoBottom()
	}
}

func (m *LogViewerModel) AppendContent(content string) {
	newLines := strings.Split(content, "\n")
	m.lines = append(m.lines, newLines...)
	if len(m.lines) > maxLogLines {
		m.lines = m.lines[len(m.lines)-maxLogLines:]
	}
	if m.ready {
		processedLines := processLines(m.lines, m.width)
		m.viewport.SetContent(strings.Join(processedLines, "\n"))
		m.viewport.GotoBottom()
	}
}

func (m *LogViewerModel) Content() string {
	return strings.Join(m.lines, "\n")
}

func (m *LogViewerModel) SetLoading(loading bool) {
	m.loading = loading
}

func (m *LogViewerModel) IsLoading() bool {
	return m.loading
}

func (m *LogViewerModel) Update(msg tea.Msg) tea.Cmd {
	var cmd tea.Cmd
	m.viewport, cmd = m.viewport.Update(msg)
	return cmd
}

func (m LogViewerModel) View() string {
	var b strings.Builder

	if m.loading {
		b.WriteString("\n\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#00ffff")).Render("  Loading logs...\n\n"))
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("  ⠋ Fetching task output"))
		b.WriteString("\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("  ⠙ Retrieving log data"))
		b.WriteString("\n")
		return b.String()
	}

	if len(m.lines) == 0 {
		b.WriteString("\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(no output)"))
		b.WriteString("\n")
		return b.String()
	}

	if m.ready {
		b.WriteString(m.viewport.View())
	} else {
		maxLines := 20
		var displayLines []string
		if len(m.lines) > maxLines {
			displayLines = m.lines[len(m.lines)-maxLines:]
		} else {
			displayLines = m.lines
		}
		w := m.width
		if w <= 0 {
			w = 80
		}
		processedLines := processLines(displayLines, w)
		b.WriteString(strings.Join(processedLines, "\n"))
	}

	return b.String()
}
