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

	listView := m.runList.View()

	var rightContent string
	if m.rightTab == TabDetail {
		rightContent = m.runDetail.View()
	} else {
		rightContent = m.logViewer.View()
	}

	tabs := renderTabs(m.rightTab, m.dims.rightContentW)
	rightView := tabs + "\n" + rightContent

	leftFocused := m.focusedPanel == FocusRunList
	rightFocused := m.focusedPanel == FocusRightPanel

	leftPanel := renderPanel(listView, leftFocused, m.dims.leftContentW, m.dims.leftContentH)
	rightPanel := renderPanel(rightView, rightFocused, m.dims.rightContentW, m.dims.rightContentH)

	gap := 2
	panels := lipgloss.JoinHorizontal(lipgloss.Top, leftPanel, strings.Repeat(" ", gap), rightPanel)

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
