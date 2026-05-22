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

	// Panel has border (1) + padding (1) on all sides = 2x4
	borderPaddingW := 4 // left and right
	borderPaddingH := 4 // top and bottom
	gap := 2 // between panels

	// Right panel has an extra line for tabs
	rightExtraH := 2

	// Calculate available content area for both panels
	totalFrameAndGapW := borderPaddingW + gap + borderPaddingW
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
		if leftContentW <16 {
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

	// Calculate the actual component sizes (content area)
	leftComponentH := totalH - borderPaddingH
	rightComponentH := totalH - borderPaddingH - rightExtraH
	if rightComponentH < 3 {
		rightComponentH =3
	}
	if leftComponentH <3 {
		leftComponentH=3
	}

	// Set components with the calculated sizes (this is handled by resizeComponents, but just in case)
	leftPanel := renderPanel(listView, leftFocused, leftContentW, totalH)
	rightPanel := renderPanel(rightView, rightFocused, rightContentW, totalH)

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
