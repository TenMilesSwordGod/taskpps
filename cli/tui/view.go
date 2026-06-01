package tui

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/tui/components"
)

var (
	lastViewHash  string
	lastRendered  string
	viewCacheHits int
)

func computeViewHash(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func (m Model) View() string {
	s := m.state
	if s.Quit {
		return ""
	}

	if !s.Ready {
		return "Initializing...\n"
	}

	header := renderHeader(s.Width)
	footer := renderFooter(s.Width, s, &m)

	leftTitle := components.TitleStyle.Render("Runs")
	if s.FocusedPanel == FocusRunList {
		leftTitle = components.CursorStyle.Render("Runs")
	}
	leftContent := leftTitle + "\n" + m.runList.View()

	tabs := renderTabs(s.RightTab, s.Dims.rightContentW)
	var rightContent string
	if s.RightTab == TabDetail {
		rightContent = tabs + "\n" + m.runDetail.View()
	} else {
		rightContent = tabs + "\n" + m.logViewer.View()
	}

	leftLines := strings.Split(leftContent, "\n")
	rightLines := strings.Split(rightContent, "\n")

	contentH := s.Dims.contentH
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
		innerB.WriteString(" ")
		innerB.WriteString(padRightVisual(leftLines[i], s.Dims.leftContentW))
		innerB.WriteString(components.DividerStyle.Render("│"))
		innerB.WriteString(padRightVisual(rightLines[i], s.Dims.rightContentW))
		innerB.WriteString(" ")
		if i < contentH-1 {
			innerB.WriteString("\n")
		}
	}

	borderColor := components.ColorCyan

	outerStyle := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(borderColor).
		Width(s.Dims.innerW).
		Height(s.Dims.contentH)

	panels := outerStyle.Render(innerB.String())

	var b strings.Builder
	b.WriteString(header)
	b.WriteString("\n")
	b.WriteString(panels)
	b.WriteString("\n")
	b.WriteString(footer)

	result := b.String()

	newHash := computeViewHash(result)
	if newHash == lastViewHash {
		viewCacheHits++
		if rec := GetDebugRecorder(); rec.IsEnabled() {
			rec.RecordEvent("VIEW_CACHE", fmt.Sprintf("HIT #%d: view unchanged, returning cached render", viewCacheHits))
		}
		return lastRendered
	}
	if rec := GetDebugRecorder(); rec.IsEnabled() && viewCacheHits > 0 {
		rec.RecordEvent("VIEW_CACHE", fmt.Sprintf("MISS after %d hits: view changed, generating new render", viewCacheHits))
		viewCacheHits = 0
	}
	lastViewHash = newHash
	lastRendered = result

	if rec := GetDebugRecorder(); rec.IsEnabled() {
		rec.RecordFrame(result)
	}

	return result
}

func padRightVisual(line string, width int) string {
	if width <= 0 {
		return ""
	}
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
		Foreground(components.ColorCyan).Bold(true)
	inactiveStyle := lipgloss.NewStyle().
		Foreground(components.ColorDim)

	var tabs string
	if activeTab == TabDetail {
		tabs = activeStyle.Render("▸ Detail") +
			inactiveStyle.Render(" · ") +
			inactiveStyle.Render("Logs")
	} else {
		tabs = inactiveStyle.Render("Detail") +
			inactiveStyle.Render(" · ") +
			activeStyle.Render("▸ Logs")
	}

	padW := width - lipgloss.Width(tabs)
	if padW > 0 {
		tabs += strings.Repeat(" ", padW)
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

func renderFooter(width int, s AppState, m *Model) string {
	bg := lipgloss.NewStyle().Background(components.ColorBarBg)

	keyStyle := lipgloss.NewStyle().Background(components.ColorBarBg).Foreground(components.ColorWhite).Bold(true)
	descStyle := lipgloss.NewStyle().Background(components.ColorBarBg).Foreground(components.ColorDim)
	sepStyle := lipgloss.NewStyle().Background(components.ColorBarBg).Foreground(components.ColorDim)
	sep := sepStyle.Render(" │ ")

	var hints []string
	switch s.FocusedPanel {
	case FocusRunList:
		hints = []string{
			keyStyle.Render("↑↓") + descStyle.Render("nav"),
			keyStyle.Render("enter") + descStyle.Render("select"),
			keyStyle.Render("tab") + descStyle.Render("panel"),
			keyStyle.Render("r") + descStyle.Render("refresh"),
			keyStyle.Render("q") + descStyle.Render("quit"),
		}
	case FocusRightPanel:
		if s.RightTab == TabDetail {
			cLabel := "expand"
			if m.runDetail.HasExpanded() {
				cLabel = "collapse"
			}
			hints = []string{
				keyStyle.Render("↑↓") + descStyle.Render("nav"),
				keyStyle.Render("enter") + descStyle.Render("expand"),
				keyStyle.Render("c") + descStyle.Render(cLabel),
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

	var hintsWidth int
	for i, h := range hints {
		if i > 0 {
			hintsWidth += lipgloss.Width(sep)
		}
		hintsWidth += lipgloss.Width(h)
	}
	hintsWidth += lipgloss.Width(bg.Render(" "))

	total := m.runList.Len()
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

	statusText := fmt.Sprintf(" Runs:%d Tasks:%d/%d %ds ", total, tasksDone, totalTasks, refreshInterval)
	statusWidth := lipgloss.Width(statusText)
	if s.ErrorMsg != "" {
		errText := fmt.Sprintf(" ERR:%s ", truncateStr(s.ErrorMsg, 20))
		statusWidth += lipgloss.Width(errText)
	}

	padW := width - hintsWidth - statusWidth
	if padW < 0 {
		padW = 0
	}

	hintsStr := bg.Render(" ") + strings.Join(hints, sep)
	statusStr := bg.Copy().Foreground(components.ColorDim).Render(statusText)
	if s.ErrorMsg != "" {
		errStr := bg.Copy().Foreground(components.ColorFailed).Bold(true).Render(
			fmt.Sprintf(" ERR:%s ", truncateStr(s.ErrorMsg, 20)))
		statusStr = errStr + statusStr
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