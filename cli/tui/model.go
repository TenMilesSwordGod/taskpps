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
	var detailTab, logsTab string

	if activeTab == TabDetail {
		detailTab = components.TabBarStyle.Copy().
			Bold(true).Foreground(components.ColorCyan).
			Render("> Detail")
	} else {
		detailTab = components.TabBarStyle.Render("  Detail")
	}

	sep := components.TabBarStyle.Render(" | ")

	if activeTab == TabLogs {
		logsTab = components.TabBarStyle.Copy().
			Bold(true).Foreground(components.ColorCyan).
			Render("> Logs")
	} else {
		logsTab = components.TabBarStyle.Render("  Logs")
	}

	tabs := detailTab + sep + logsTab

	textWidth := lipgloss.Width(tabs)
	if textWidth < width {
		pad := components.TabBarStyle.Render(strings.Repeat(" ", width-textWidth))
		tabs += pad
	}

	return tabs
}

func renderHeader(width int) string {
	help := "[q]uit  [tab]panel  [t]abs  [↑↓/jk]nav  [enter]select  [r]efresh"

	headerBg := lipgloss.NewStyle().Background(lipgloss.Color("#333333"))

	left := headerBg.Copy().
		Foreground(components.ColorCyan).Bold(true).
		Render(" ppsctl watch ")

	right := headerBg.Copy().
		Foreground(components.ColorWhite).
		Render(help)

	spacerLen := width - lipgloss.Width(" ppsctl watch ") - lipgloss.Width(help) - 2
	if spacerLen < 1 {
		spacerLen = 1
	}
	spacer := headerBg.Render(strings.Repeat(" ", spacerLen))

	margin := headerBg.Render(" ")

	return margin + left + spacer + right + margin
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

	status := fmt.Sprintf("Runs: %d | Tasks: %d/%d | Polling every 2s", total, tasksDone, totalTasks)
	return components.FooterStyle.Width(width).Render(status)
}
