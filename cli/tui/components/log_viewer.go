package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type LogViewerModel struct {
	viewport viewport.Model
	content  strings.Builder
	ready    bool
}

func NewLogViewerModel() LogViewerModel {
	return LogViewerModel{}
}

func (m *LogViewerModel) SetSize(w, h int) {
	if !m.ready {
		m.viewport = viewport.New(w, h-2)
		m.viewport.YPosition = 0
		m.ready = true
	} else {
		m.viewport.Width = w
		m.viewport.Height = h - 2
	}
	m.viewport.SetContent(m.content.String())
	m.viewport.GotoBottom()
}

func (m *LogViewerModel) SetContent(content string) {
	m.content.Reset()
	m.content.WriteString(content)
	if m.ready {
		m.viewport.SetContent(content)
		m.viewport.GotoBottom()
	}
}

func (m *LogViewerModel) AppendContent(content string) {
	m.content.WriteString(content)
	if m.ready {
		m.viewport.SetContent(m.content.String())
		m.viewport.GotoBottom()
	}
}

func (m *LogViewerModel) Content() string {
	return m.content.String()
}

func (m LogViewerModel) Update(msg tea.Msg) (LogViewerModel, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "pgup":
			m.viewport.ViewUp()
		case "pgdown":
			m.viewport.ViewDown()
		case "home":
			m.viewport.GotoTop()
		case "end":
			m.viewport.GotoBottom()
		default:
			m.viewport, cmd = m.viewport.Update(msg)
		}
	default:
		m.viewport, cmd = m.viewport.Update(msg)
	}
	return m, cmd
}

func (m LogViewerModel) View() string {
	var b strings.Builder

	title := TitleStyle.Render("Logs")
	b.WriteString(title)
	b.WriteString("\n\n")

	if m.content.Len() == 0 {
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(no output)"))
		return b.String()
	}

	var vpContent string
	if m.ready {
		vpContent = fmt.Sprintf("%s\n%s", m.viewport.View(), "(scroll with PgUp/PgDown)")
	} else {
		lines := strings.Split(m.content.String(), "\n")
		maxLines := 20
		if len(lines) > maxLines {
			lines = lines[len(lines)-maxLines:]
		}
		vpContent = strings.Join(lines, "\n")
	}
	b.WriteString(vpContent)

	return b.String()
}