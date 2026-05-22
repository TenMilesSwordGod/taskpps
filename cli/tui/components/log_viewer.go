package components

import (
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

const maxLogLines = 5000 // Keep last 5000 lines of logs

type LogViewerModel struct {
	viewport viewport.Model
	lines    []string
	ready    bool
	width    int // Store current width for line wrapping/truncation
}

func NewLogViewerModel() LogViewerModel {
	return LogViewerModel{}
}

// Helper to process a single line: truncate if too long for the given width
func processLine(line string, width int) string {
	if width <= 0 {
		width = 80 // Default if no width set
	}
	if len(line) > width {
		if width > 3 {
			return line[:width-3] + "..."
		}
		return line[:width]
	}
	return line
}

// Process all lines for display
func processLines(lines []string, width int) []string {
	processed := make([]string, len(lines))
	for i, line := range lines {
		processed[i] = processLine(line, width)
	}
	return processed
}

func (m *LogViewerModel) SetSize(w, h int) {
	m.width = w
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
	if len(m.lines) > maxLogLines {
		m.lines = m.lines[len(m.lines)-maxLogLines:]
	}
	if m.ready {
		processedLines := processLines(m.lines, m.width)
		// Save scroll position before updating content
		oldY := m.viewport.YPosition
		m.viewport.SetContent(strings.Join(processedLines, "\n"))
		m.viewport.YPosition = oldY
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

func (m *LogViewerModel) Update(msg tea.Msg) tea.Cmd {
	var cmd tea.Cmd
	m.viewport, cmd = m.viewport.Update(msg)
	return cmd
}

func (m LogViewerModel) View() string {
	var b strings.Builder

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
		processedLines := processLines(displayLines, m.width)
		b.WriteString(strings.Join(processedLines, "\n"))
	}

	return b.String()
}
