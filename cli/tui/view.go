package tui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/tui/components"
)

func (m Model) View() string {
	if m.quit {
		return ""
	}

	if !m.ready {
		return "Initializing...\n"
	}

	header := renderHeader(m.width)
	footer := renderFooter(m.width, m)

	errLine := ""
	if m.errMsg != "" {
		errLine = components.ErrorStyle.Render(fmt.Sprintf(" ERROR: %s ", m.errMsg))
	}

	headerH := lipgloss.Height(header)
	footerH := lipgloss.Height(footer)
	errH := lipgloss.Height(errLine)
	availableH := m.height - headerH - footerH - errH
	if availableH < 5 {
		availableH = 5
	}

	borderW := 2
	paddingW := 2
	panelOverhead := borderW + paddingW
	totalOverhead := panelOverhead * 3

	availableW := m.width - totalOverhead
	if availableW < 30 {
		availableW = 30
	}

	listContentW := availableW * 25 / 100
	detailContentW := availableW * 35 / 100
	logContentW := availableW - listContentW - detailContentW

	if listContentW < 10 {
		listContentW = 10
		detailContentW = availableW * 40 / 100
		logContentW = availableW - listContentW - detailContentW
	}
	if logContentW < 10 {
		logContentW = 10
	}

	contentH := availableH - borderW

	listView := m.runList.View()
	detailView := m.runDetail.View()
	logView := m.logViewer.View()

	listPanel := renderPanel(listView, m.focusedPanel == FocusRunList, listContentW, contentH)
	detailPanel := renderPanel(detailView, m.focusedPanel == FocusRunDetail, detailContentW, contentH)
	logPanel := renderPanel(logView, m.focusedPanel == FocusLogViewer, logContentW, contentH)

	panels := lipgloss.JoinHorizontal(lipgloss.Top, listPanel, detailPanel, logPanel)

	var b strings.Builder
	b.WriteString(header)
	b.WriteString("\n")
	b.WriteString(panels)
	if errLine != "" {
		b.WriteString("\n")
		b.WriteString(errLine)
	}
	b.WriteString("\n")
	b.WriteString(footer)

	return b.String()
}
