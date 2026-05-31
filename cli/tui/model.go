package tui

import (
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

type PanelFocus int

const (
	FocusRunList PanelFocus = iota
	FocusRightPanel
)

type RightPanelTab int

const (
	TabDetail RightPanelTab = iota
	TabLogs
)

type layoutDims struct {
	leftContentW  int
	rightContentW int
	leftContentH  int
	rightContentH int
	panelH        int
}

type Model struct {
	runList   components.RunListModel
	runDetail components.RunDetailModel
	logViewer components.LogViewerModel

	focusedPanel PanelFocus
	rightTab     RightPanelTab

	client      *client.Client
	targetRunID string

	runs   []models.Run
	errMsg string

	width  int
	height int
	ready  bool
	quit   bool
	dims   layoutDims
}

func StartWatch(c *client.Client, runID string) error {
	m := NewModel(c, runID)
	p := tea.NewProgram(m, tea.WithAltScreen())
	_, err := p.Run()
	return err
}

func NewModel(c *client.Client, runID string) Model {
	return Model{
		runList:      components.NewRunListModel(),
		runDetail:    components.NewRunDetailModel(),
		logViewer:    components.NewLogViewerModel(),
		focusedPanel: FocusRunList,
		client:       c,
		targetRunID:  runID,
	}
}

func (m Model) Init() tea.Cmd {
	return tea.Batch(
		fetchRuns(m.client),
		tea.Tick(2*time.Second, func(_ time.Time) tea.Msg {
			return tickMsg{}
		}),
	)
}

func fetchRuns(c *client.Client) tea.Cmd {
	return func() tea.Msg {
		resp, err := c.ListRuns("", "", 50)
		if err != nil {
			return runsFetchedMsg{err: err}
		}
		return runsFetchedMsg{runs: resp.Items}
	}
}

func fetchRun(c *client.Client, runID string) tea.Cmd {
	return func() tea.Msg {
		run, err := c.GetRun(runID)
		if err != nil {
			return runFetchedMsg{err: err}
		}
		return runFetchedMsg{run: run}
	}
}

func fetchLogs(c *client.Client, runID, taskName string) tea.Cmd {
	return func() tea.Msg {
		logs, err := c.GetLogs(runID, taskName, 500)
		if err != nil {
			return logsFetchedMsg{err: err}
		}
		return logsFetchedMsg{logs: logs}
	}
}

func (m Model) focusNext() PanelFocus {
	switch m.focusedPanel {
	case FocusRunList:
		return FocusRightPanel
	default:
		return FocusRunList
	}
}

func (m Model) focusPrev() PanelFocus {
	switch m.focusedPanel {
	case FocusRunList:
		return FocusRightPanel
	default:
		return FocusRunList
	}
}

func (m Model) cycleTab() RightPanelTab {
	if m.rightTab == TabDetail {
		return TabLogs
	}
	return TabDetail
}

func (m *Model) navigateBack() {
	if m.focusedPanel == FocusRightPanel {
		if m.rightTab == TabLogs {
			m.rightTab = TabDetail
		} else {
			m.focusedPanel = FocusRunList
		}
	}
}

func (m *Model) navigatePrevPipeline() tea.Cmd {
	if len(m.runs) == 0 {
		return nil
	}
	cur := m.runList.SelectedRun()
	if cur == nil {
		return nil
	}
	curIdx := -1
	for i, r := range m.runs {
		if r.ID == cur.ID {
			curIdx = i
			break
		}
	}
	if curIdx <= 0 {
		return nil
	}
	prevRun := &m.runs[curIdx-1]
	m.runList.SetCursor(curIdx - 1)
	m.runDetail.SetRun(prevRun)
	m.rightTab = TabDetail
	return fetchRun(m.client, prevRun.ID)
}

func (m *Model) navigateNextPipeline() tea.Cmd {
	if len(m.runs) == 0 {
		return nil
	}
	cur := m.runList.SelectedRun()
	if cur == nil {
		return nil
	}
	curIdx := -1
	for i, r := range m.runs {
		if r.ID == cur.ID {
			curIdx = i
			break
		}
	}
	if curIdx >= len(m.runs)-1 {
		return nil
	}
	nextRun := &m.runs[curIdx+1]
	m.runList.SetCursor(curIdx + 1)
	m.runDetail.SetRun(nextRun)
	m.rightTab = TabDetail
	return fetchRun(m.client, nextRun.ID)
}

func renderPanel(panelContent string, focused bool, contentWidth, contentHeight int) string {
	style := components.PanelStyle.
		Width(contentWidth + 4).
		Height(contentHeight + 2)
	if focused {
		style = components.FocusedPanelStyle.
			Width(contentWidth + 4).
			Height(contentHeight + 2)
	}
	return style.Render(panelContent)
}

func renderTabs(activeTab RightPanelTab, width int) string {
	tabBg := lipgloss.Color("#333333")
	activeFg := components.ColorCyan
	inactiveFg := lipgloss.Color("#888888")

	detailLabel := "Detail"
	logsLabel := "Logs"

	if activeTab == TabDetail {
		detailTab := lipgloss.NewStyle().
			Background(tabBg).Foreground(activeFg).Bold(true).
			Render(" ▸ " + detailLabel + " ")
		underline := lipgloss.NewStyle().
			Background(tabBg).Foreground(activeFg).
			Render(strings.Repeat("━", len(detailLabel)+2))
		detailTab += "\n" + underline

		logsTab := lipgloss.NewStyle().
			Background(tabBg).Foreground(inactiveFg).
			Render("   " + logsLabel + " ")
		logsTab += "\n" + lipgloss.NewStyle().
			Background(tabBg).Foreground(inactiveFg).
			Render(strings.Repeat("─", len(logsLabel)+2))

		tabs := lipgloss.JoinHorizontal(lipgloss.Bottom, detailTab, "  ", logsTab)
		textWidth := lipgloss.Width(tabs)
		if textWidth < width {
			pad := lipgloss.NewStyle().Background(tabBg).Render(strings.Repeat(" ", width-textWidth))
			tabs += pad
		}
		return tabs
	}

	detailTab := lipgloss.NewStyle().
		Background(tabBg).Foreground(inactiveFg).
		Render("   " + detailLabel + " ")
	detailTab += "\n" + lipgloss.NewStyle().
		Background(tabBg).Foreground(inactiveFg).
		Render(strings.Repeat("─", len(detailLabel)+2))

	logsTab := lipgloss.NewStyle().
		Background(tabBg).Foreground(activeFg).Bold(true).
		Render(" ▸ " + logsLabel + " ")
	underline := lipgloss.NewStyle().
		Background(tabBg).Foreground(activeFg).
		Render(strings.Repeat("━", len(logsLabel)+2))
	logsTab += "\n" + underline

	tabs := lipgloss.JoinHorizontal(lipgloss.Bottom, detailTab, "  ", logsTab)
	textWidth := lipgloss.Width(tabs)
	if textWidth < width {
		pad := lipgloss.NewStyle().Background(tabBg).Render(strings.Repeat(" ", width-textWidth))
		tabs += pad
	}
	return tabs
}

func renderHeader(width int) string {
	headerBg := lipgloss.NewStyle().Background(lipgloss.Color("#333333"))

	left := headerBg.Copy().
		Foreground(components.ColorCyan).Bold(true).
		Render(" ppsctl watch ")

	right := headerBg.Copy().
		Foreground(components.ColorWhite).
		Render(" pipeline task monitor ")

	spacerLen := width - lipgloss.Width(" ppsctl watch ") - lipgloss.Width(" pipeline task monitor ") - 2
	if spacerLen < 1 {
		spacerLen = 1
	}
	spacer := headerBg.Render(strings.Repeat(" ", spacerLen))

	margin := headerBg.Render(" ")

	return margin + left + spacer + right + margin
}

func contextKeyHints(m Model) string {
	keyStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#AAAAAA")).Bold(true)
	descStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#888888"))
	sep := descStyle.Render("  ")

	switch m.focusedPanel {
	case FocusRunList:
		hints := []string{
			keyStyle.Render("↑↓") + descStyle.Render("/jk"),
			descStyle.Render("navigate"),
			keyStyle.Render("enter"),
			descStyle.Render("select"),
			keyStyle.Render("tab"),
			descStyle.Render("panel"),
			keyStyle.Render("r"),
			descStyle.Render("refresh"),
			keyStyle.Render("q"),
			descStyle.Render("quit"),
		}
		return sep + strings.Join(hints, sep)

	case FocusRightPanel:
		switch m.rightTab {
		case TabDetail:
			hints := []string{
				keyStyle.Render("↑↓") + descStyle.Render("/jk"),
				descStyle.Render("navigate"),
				keyStyle.Render("enter"),
				descStyle.Render("expand/select"),
				keyStyle.Render("c"),
				descStyle.Render("collapse/expand all"),
				keyStyle.Render("b"),
				descStyle.Render("back"),
				keyStyle.Render("p/n"),
				descStyle.Render("prev/next pipeline"),
				keyStyle.Render("t"),
				descStyle.Render("logs"),
				keyStyle.Render("tab"),
				descStyle.Render("runlist"),
				keyStyle.Render("q"),
				descStyle.Render("quit"),
			}
			return sep + strings.Join(hints, sep)

		case TabLogs:
			hints := []string{
				keyStyle.Render("↑↓"),
				descStyle.Render("scroll"),
				keyStyle.Render("b"),
				descStyle.Render("back"),
				keyStyle.Render("p/n"),
				descStyle.Render("prev/next pipeline"),
				keyStyle.Render("t"),
				descStyle.Render("detail"),
				keyStyle.Render("tab"),
				descStyle.Render("runlist"),
				keyStyle.Render("q"),
				descStyle.Render("quit"),
			}
			return sep + strings.Join(hints, sep)
		}
	}
	return ""
}

func renderFooter(width int, m Model) string {
	total := len(m.runs)
	tasksDone := 0
	totalTasks := 0
	sel := m.runList.SelectedRun()
	if sel != nil {
		for _, t := range sel.Tasks {
			totalTasks++
			if t.Status == "success" || t.Status == "failed" || t.Status == "skipped" {
				tasksDone++
			}
		}
	}

	footerBg := lipgloss.NewStyle().Background(lipgloss.Color("#333333"))

	statusText := fmt.Sprintf(" Runs: %d | Tasks: %d/%d | 2s ", total, tasksDone, totalTasks)
	status := footerBg.Copy().
		Foreground(components.ColorWhite).
		Render(statusText)

	hints := footerBg.Copy().
		Foreground(components.ColorWhite).
		Render(contextKeyHints(m))

	hintsWidth := lipgloss.Width(hints)
	statusWidth := lipgloss.Width(status)
	spacerLen := width - hintsWidth - statusWidth
	if spacerLen < 0 {
		spacerLen = 0
	}
	spacer := footerBg.Render(strings.Repeat(" ", spacerLen))

	return hints + spacer + status
}
