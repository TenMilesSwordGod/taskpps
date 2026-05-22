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

	totalW := m.width
	totalH := availableH

	// Must match resizeComponents calculations
	borderOverheadW := 4 // border(2) + padding(2)
	borderOverheadH := 2 // border(2) only
	gap := 2             // between panels

	totalFrameAndGapW := borderOverheadW + gap + borderOverheadW
	contentW := totalW - totalFrameAndGapW
	if contentW < 42 {
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
			leftContentW = 16
			rightContentW = 26
		}
	}

	listView := m.runList.View()

	var rightContent string
	if m.rightTab == TabDetail {
		rightContent = m.runDetail.View()
	} else {
		rightContent = m.logViewer.View()
	}

	tabs := renderTabs(m.rightTab, rightContentW)
	rightView := tabs + "\n" + rightContent

	leftFocused := m.focusedPanel == FocusRunList
	rightFocused := m.focusedPanel == FocusRightPanel

	leftPanel := renderPanel(listView, leftFocused, leftContentW, totalH-borderOverheadH)
	rightPanel := renderPanel(rightView, rightFocused, rightContentW, totalH-borderOverheadH)

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
