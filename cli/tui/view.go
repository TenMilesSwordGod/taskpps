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
	gap := 2

	// Calculate actual content widths (inside panels)
	totalFrameAndGapW := panelFrameW + gap + panelFrameW
	contentW := w - totalFrameAndGapW
	if contentW < 42 { // 16 +26 =42 min content width
		contentW = 42
	}
	leftContentW := contentW * 20 / 100
	rightContentW := contentW - leftContentW

	if leftContentW < 16 {
		leftContentW = 16
		rightContentW = contentW - leftContentW
	}
	if rightContentW < 26 {
		rightContentW = 26
		leftContentW = contentW - rightContentW
		if leftContentW < 16 {
			leftContentW =16
			rightContentW =26
			// if even that is too big, just use min sizes
		}
	}

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

	leftPanel := renderPanel(listView, leftFocused, leftContentW, h)
	rightPanel := renderPanel(rightView, rightFocused, rightContentW, h)

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
