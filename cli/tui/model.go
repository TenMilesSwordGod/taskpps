package tui

import (
	"fmt"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/logger"
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

type Model struct {
	runList    components.RunListModel
	runDetail  components.RunDetailModel
	logViewer  components.LogViewerModel

	focusedPanel PanelFocus
	rightTab     RightPanelTab

	client      *client.Client
	targetRunID string

	runs        []models.Run
	errMsg      string

	width  int
	height int
	ready  bool
	quit   bool
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

func renderPanel(panel string, focused bool, contentWidth, contentHeight int) string {
	// Panel will add its own padding and border, so total size is content + frame
	style := components.PanelStyle.Width(contentWidth).Height(contentHeight)
	if focused {
		style = components.FocusedPanelStyle.Width(contentWidth).Height(contentHeight)
	}
	return style.Render(panel)
}

func renderTabs(activeTab RightPanelTab, width int) string {
	detailTab := "Detail"
	logsTab := "Logs"

	if activeTab == TabDetail {
		detailTab = components.CursorStyle.Render("> " + detailTab)
	} else {
		detailTab = "  " + detailTab
	}

	if activeTab == TabLogs {
		logsTab = components.CursorStyle.Render("> " + logsTab)
	} else {
		logsTab = "  " + logsTab
	}

	tabs := detailTab + " | " + logsTab
	return components.HeaderStyle.Width(width).Render(tabs)
}

func renderHeader(width int) string {
	help := "[q]uit  [tab]panel  [t]abs  [↑↓/jk]nav  [enter]select  [r]efresh"
	left := components.TitleStyle.Render(" ppsctl watch ")
	right := lipgloss.NewStyle().Foreground(components.ColorWhite).Render(help)
	spacer := width - lipgloss.Width(left) - lipgloss.Width(right) - 2
	if spacer < 1 {
		spacer = 1
	}
	return components.HeaderStyle.Width(width).Render(left + fmt.Sprintf("%*s", spacer, "") + right)
}

func renderFooter(width int, m Model) string {
	total := len(m.runs)
	tasksDone := 0
	totalTasks := 0
	if m.runDetail.SelectedTask() != nil {
		sel := m.runList.SelectedRun()
		if sel != nil {
			for _, t := range sel.Tasks {
				totalTasks++
				if t.Status == "success" || t.Status == "failed" || t.Status == "skipped" {
					tasksDone++
				}
			}
		}
	}

	status := fmt.Sprintf("Runs: %d | Tasks: %d/%d | Polling every 2s", total, tasksDone, totalTasks)
	return components.FooterStyle.Width(width).Render(status)
}