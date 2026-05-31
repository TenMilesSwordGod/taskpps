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

	leftTitle := components.TitleStyle.Render("Runs")
	if m.focusedPanel == FocusRunList {
		leftTitle = components.CursorStyle.Render("Runs")
	}
	leftContent := leftTitle + "\n" + m.runList.View()

	tabs := renderTabs(m.rightTab, m.dims.rightContentW)
	var rightContent string
	if m.rightTab == TabDetail {
		rightContent = tabs + "\n" + m.runDetail.View()
	} else {
		rightContent = tabs + "\n" + m.logViewer.View()
	}

	leftLines := strings.Split(leftContent, "\n")
	rightLines := strings.Split(rightContent, "\n")

	contentH := m.dims.contentH
	for len(leftLines) < contentH {
		leftLines = append(leftLines, "")
	}
	if len(leftLines) > contentH {
		leftLines = leftLines[:contentH]
	}
	for len(rightLines) < contentH {
		rightLines = append(rightLines, "")
	}
	if len(rightLines) > contentH {
		rightLines = rightLines[:contentH]
	}

	var innerB strings.Builder
	for i := 0; i < contentH; i++ {
		innerB.WriteString(padRightVisual(leftLines[i], m.dims.leftContentW))
		innerB.WriteString(components.DividerStyle.Render("│"))
		innerB.WriteString(padRightVisual(rightLines[i], m.dims.rightContentW))
		if i < contentH-1 {
			innerB.WriteString("\n")
		}
	}

	borderColor := components.ColorBorder
	if m.focusedPanel == FocusRunList {
		borderColor = components.ColorCyan
	}

	outerStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(borderColor).
		Padding(0, 1).
		Width(m.dims.innerW).
		Height(m.dims.panelH)

	panels := outerStyle.Render(innerB.String())

	var b strings.Builder
	b.WriteString(header)
	b.WriteString("\n")
	b.WriteString(panels)
	b.WriteString("\n")
	b.WriteString(footer)

	return b.String()
}

func padRightVisual(line string, width int) string {
	visualW := lipgloss.Width(line)
	if visualW > width {
		return components.TruncateLine(line, width)
	}
	if visualW < width {
		return line + strings.Repeat(" ", width-visualW)
	}
	return line
}

func renderTabs(activeTab RightPanelTab, width int) string {
	activeStyle := lipgloss.NewStyle().
		Background(components.ColorBarBg).
		Foreground(components.ColorCyan).Bold(true)
	inactiveStyle := lipgloss.NewStyle().
		Background(components.ColorBarBg).
		Foreground(components.ColorDim)

	var tabs string
	if activeTab == TabDetail {
		tabs = activeStyle.Render(" ▸ Detail ") +
			inactiveStyle.Render(" │ ") +
			inactiveStyle.Render("  Logs ")
	} else {
		tabs = inactiveStyle.Render("  Detail ") +
			inactiveStyle.Render(" │ ") +
			activeStyle.Render(" ▸ Logs ")
	}

	padW := width - lipgloss.Width(tabs)
	if padW > 0 {
		tabs += lipgloss.NewStyle().Background(components.ColorBarBg).Render(strings.Repeat(" ", padW))
	}

	return tabs
}

func renderHeader(width int) string {
	bg := lipgloss.NewStyle().Background(components.ColorBarBg)

	left := bg.Copy().
		Foreground(components.ColorCyan).Bold(true).
		Render(" ppsctl watch ")

	right := bg.Copy().
		Foreground(components.ColorDim).
		Render(" pipeline task monitor ")

	padW := width - lipgloss.Width(left) - lipgloss.Width(right)
	if padW < 1 {
		padW = 1
	}
	spacer := bg.Render(strings.Repeat(" ", padW))

	return left + spacer + right
}

func renderFooter(width int, m Model) string {
	bg := lipgloss.NewStyle().Background(components.ColorBarBg)

	keyStyle := lipgloss.NewStyle().Background(components.ColorBarBg).Foreground(components.ColorWhite).Bold(true)
	descStyle := lipgloss.NewStyle().Background(components.ColorBarBg).Foreground(components.ColorDim)
	sepStyle := lipgloss.NewStyle().Background(components.ColorBarBg).Foreground(components.ColorDim)
	sep := sepStyle.Render(" │ ")

	var hints []string
	switch m.focusedPanel {
	case FocusRunList:
		hints = []string{
			keyStyle.Render("↑↓") + descStyle.Render("nav"),
			keyStyle.Render("enter") + descStyle.Render("select"),
			keyStyle.Render("tab") + descStyle.Render("panel"),
			keyStyle.Render("r") + descStyle.Render("refresh"),
			keyStyle.Render("q") + descStyle.Render("quit"),
		}
	case FocusRightPanel:
		if m.rightTab == TabDetail {
			hints = []string{
				keyStyle.Render("↑↓") + descStyle.Render("nav"),
				keyStyle.Render("enter") + descStyle.Render("expand"),
				keyStyle.Render("c") + descStyle.Render("collapse"),
				keyStyle.Render("b") + descStyle.Render("back"),
				keyStyle.Render("p/n") + descStyle.Render("pipeline"),
				keyStyle.Render("t") + descStyle.Render("logs"),
				keyStyle.Render("q") + descStyle.Render("quit"),
			}
		} else {
			hints = []string{
				keyStyle.Render("↑↓") + descStyle.Render("scroll"),
				keyStyle.Render("b") + descStyle.Render("back"),
				keyStyle.Render("p/n") + descStyle.Render("pipeline"),
				keyStyle.Render("t") + descStyle.Render("detail"),
				keyStyle.Render("q") + descStyle.Render("quit"),
			}
		}
	}

	hintsStr := bg.Render(" ") + strings.Join(hints, sep)

	total := len(m.runs)
	tasksDone := 0
	totalTasks := 0
	sel := m.runList.SelectedRun()
	if sel != nil {
		for _, t := range sel.Tasks {
			totalTasks++
			if t.Status == "success" || t.Status == "failed" || t.Status == "skipped" || t.Status == "cancelled" {
				tasksDone++
			}
		}
	}

	statusStr := bg.Copy().Foreground(components.ColorDim).Render(
		fmt.Sprintf(" Runs:%d Tasks:%d/%d %ds ", total, tasksDone, totalTasks, refreshInterval))

	if m.errMsg != "" {
		errStr := bg.Copy().Foreground(components.ColorFailed).Bold(true).Render(
			fmt.Sprintf(" ERR:%s ", truncateStr(m.errMsg, 20)))
		statusStr = errStr + statusStr
	}

	padW := width - lipgloss.Width(hintsStr) - lipgloss.Width(statusStr)
	if padW < 0 {
		padW = 0
	}
	spacer := bg.Render(strings.Repeat(" ", padW))

	return hintsStr + spacer + statusStr
}

func truncateStr(s string, maxLen int) string {
	runes := []rune(s)
	if len(runes) <= maxLen {
		return s
	}
	if maxLen <= 3 {
		return ""
	}
	return string(runes[:maxLen-3]) + "..."
}
