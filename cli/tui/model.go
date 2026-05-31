package tui

import (
	"time"

	tea "github.com/charmbracelet/bubbletea"
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
	innerW        int
	leftContentW  int
	rightContentW int
	panelH        int
	contentH      int
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

const refreshInterval = 2

func (m Model) Init() tea.Cmd {
	return tea.Batch(
		fetchRuns(m.client),
		tea.Tick(time.Duration(refreshInterval)*time.Second, func(_ time.Time) tea.Msg {
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
	if m.focusedPanel == FocusRunList {
		return FocusRightPanel
	}
	return FocusRunList
}

func (m Model) focusPrev() PanelFocus {
	return m.focusNext()
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
