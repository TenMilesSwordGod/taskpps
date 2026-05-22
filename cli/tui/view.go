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

	// Panel border (1 each side) + padding (1 each side) = 4 total
	panelFrameW := 4
	panelFrameH := 4
	gap := 2

	// 2-panel layout: left (run list) + right (detail/logs tabbed)
	// Available width for both panels' content + frames + gap
	// leftContentW + panelFrameW + gap + rightContentW + panelFrameW = w
	// leftContentW = 20% of remaining after frames
	contentW := w - panelFrameW - gap - panelFrameW
	leftContentW := contentW * 20 / 100
	rightContentW := contentW - leftContentW

	if leftContentW < 16 {
		leftContentW = 16
	}
	if rightContentW < 26 {
		rightContentW = 26
	}

	// Panel total sizes (content + frame)
	leftPanelW := leftContentW + panelFrameW
	rightPanelW := rightContentW + panelFrameW

	listView := m.runList.View()

	// Determine which content to show in right panel based on active tab
	var rightContent string
	if m.rightTab == TabDetail {
		rightContent = m.runDetail.View()
	} else {
		rightContent = m.logViewer.View()
	}

	// Add tabs to right panel content
	tabs := renderTabs(m.rightTab, rightContentW)
	rightView := tabs + "\n" + rightContent

	leftFocused := m.focusedPanel == FocusRunList
	rightFocused := m.focusedPanel == FocusRightPanel

	leftPanel := renderPanel(listView, leftFocused, leftPanelW, h)
	rightPanel := renderPanel(rightView, rightFocused, rightPanelW, h)

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
