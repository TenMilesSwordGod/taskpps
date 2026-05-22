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

	// Get panel sizes from resizeComponents logic (consistent)
	w := m.width
	h := availableH

	listW := w * 25 / 100
	detailW := w * 35 / 100
	logW := w - listW - detailW - 6 // 6 = 2*3 for borders

	if listW < 15 {
		listW = 15
	}
	if detailW < 20 {
		detailW = 20
	}
	if logW < 20 {
		logW = 20
	}

	listView := m.runList.View()
	detailView := m.runDetail.View()
	logView := m.logViewer.View()

	listPanel := renderPanel(listView, m.focusedPanel == FocusRunList, listW, h)
	detailPanel := renderPanel(detailView, m.focusedPanel == FocusRunDetail, detailW, h)
	logPanel := renderPanel(logView, m.focusedPanel == FocusLogViewer, logW, h)

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
