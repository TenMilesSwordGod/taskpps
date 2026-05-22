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

	w := m.width
	h := availableH

	// 2-panel layout: left (run list) + right (detail/logs tabbed)
	// Left panel: 20% width
	// Right panel: remaining width
	leftW := w * 20 / 100
	rightW := w - leftW - 2 // 2px gap between panels

	if leftW < 20 {
		leftW = 20
	}
	if rightW < 30 {
		rightW = 30
	}

	listView := m.runList.View()
	
	// Determine which content to show in right panel based on active tab
	var rightView string
	if m.rightTab == TabDetail {
		rightView = m.runDetail.View()
	} else {
		rightView = m.logViewer.View()
	}

	leftFocused := m.focusedPanel == FocusRunList
	rightFocused := m.focusedPanel == FocusRightPanel

	leftPanel := renderPanel(listView, leftFocused, leftW, h)
	rightPanel := renderPanel(rightView, rightFocused, rightW, h)

	panels := lipgloss.JoinHorizontal(lipgloss.Top, leftPanel, rightPanel)

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
