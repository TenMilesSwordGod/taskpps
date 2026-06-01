package tui

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
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
	state AppState

	runList      components.RunListModel
	runDetail    components.RunDetailModel
	logViewer    components.LogViewerModel

	client      *client.Client
	targetRunID string

	lastUserActivityTime time.Time
	debounceTimer        *time.Timer
	pendingRender        bool
}

func StartWatch(c *client.Client, runID string, opts ...tea.ProgramOption) error {
	m := NewModel(c, runID)

	recorder := GetDebugRecorder()
	if recorder.IsEnabled() {
		recorder.RecordEvent("START", "Starting watch command")
	}

	defaultOpts := []tea.ProgramOption{tea.WithAltScreen()}
	allOpts := append(defaultOpts, opts...)
	p := tea.NewProgram(m, allOpts...)
	_, err := p.Run()

	exitCode := 0
	if err != nil {
		exitCode = 1
	}
	DisableDebugRecorder(exitCode)

	return err
}

func NewModel(c *client.Client, runID string) Model {
	return Model{
		state:       NewAppState(),
		runList:     components.NewRunListModel(),
		runDetail:   components.NewRunDetailModel(),
		logViewer:   components.NewLogViewerModel(),
		client:      c,
		targetRunID: runID,
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

func fetchLogsSync(c *client.Client, runID, taskName string) (map[string]string, error) {
	return c.GetLogs(runID, taskName, 500)
}

func (m Model) focusNext() PanelFocus {
	if m.state.FocusedPanel == FocusRunList {
		return FocusRightPanel
	}
	return FocusRunList
}

func (m Model) focusPrev() PanelFocus {
	return m.focusNext()
}

func (m Model) cycleTab() RightPanelTab {
	if m.state.RightTab == TabDetail {
		return TabLogs
	}
	return TabDetail
}

func (m *Model) navigateBack() {
	s := &m.state
	if s.FocusedPanel == FocusRightPanel {
		if s.RightTab == TabLogs {
			s.RightTab = TabDetail
		} else {
			s.FocusedPanel = FocusRunList
		}
	}
}

func (m *Model) navigatePrevPipeline() tea.Cmd {
	s := &m.state
	if len(s.Runs) == 0 {
		return nil
	}
	cur := m.runList.SelectedRun()
	if cur == nil {
		return nil
	}
	curIdx := -1
	for i, r := range s.Runs {
		if r.ID == cur.ID {
			curIdx = i
			break
		}
	}
	if curIdx <= 0 {
		return nil
	}
	s.RunListCursor = curIdx - 1
	m.runList.SetCursor(curIdx - 1)
	prevRun := &s.Runs[curIdx-1]
	m.runDetail.SetRun(prevRun)
	s.SelectedRun = prevRun
	s.RightTab = TabDetail
	return fetchRun(m.client, prevRun.ID)
}

func (m *Model) navigateNextPipeline() tea.Cmd {
	s := &m.state
	if len(s.Runs) == 0 {
		return nil
	}
	cur := m.runList.SelectedRun()
	if cur == nil {
		return nil
	}
	curIdx := -1
	for i, r := range s.Runs {
		if r.ID == cur.ID {
			curIdx = i
			break
		}
	}
	if curIdx >= len(s.Runs)-1 {
		return nil
	}
	s.RunListCursor = curIdx + 1
	m.runList.SetCursor(curIdx + 1)
	nextRun := &s.Runs[curIdx+1]
	m.runDetail.SetRun(nextRun)
	s.SelectedRun = nextRun
	s.RightTab = TabDetail
	return fetchRun(m.client, nextRun.ID)
}

const (
	debounceInterval     = 30 * time.Millisecond
	userActivityCooldown = 500 * time.Millisecond
)

func computeRunsHash(runs []models.Run) string {
	data, _ := json.Marshal(runs)
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

func computeRunHash(run *models.Run) string {
	if run == nil {
		return ""
	}
	data, _ := json.Marshal(run)
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

func (m *Model) recordUserActivity() {
	m.lastUserActivityTime = time.Now()
}

func (m *Model) shouldSkipTick() bool {
	if m.lastUserActivityTime.IsZero() {
		return false
	}
	return time.Since(m.lastUserActivityTime) < userActivityCooldown
}

func (m *Model) syncComponentsFromState() {
	s := m.state
	m.runList.SetRuns(s.Runs)
	m.runList.SetCursor(s.RunListCursor)

	if s.SelectedRun != nil {
		cp := *s.SelectedRun
		m.runDetail.SetRun(&cp)
		m.runDetail.SetCursor(s.DetailCursor)
		for k := range s.DetailExpanded {
			_ = k
		}
		for k := range s.SubExpanded {
			_ = k
		}
	}

	m.logViewer.SetContent(s.LogContent)
	m.logViewer.SetLoading(s.LogLoading)
}

func (m *Model) syncStateFromComponents() {
	s := &m.state
	s.RunListCursor = m.runList.Cursor()
	s.DetailCursor = m.runDetail.Cursor()
	if sel := m.runDetail.SelectedRun(); sel != nil {
		s.SelectedRun = sel
	}
	if task := m.runDetail.SelectedTask(); task != nil {
		s.SelectedTask = task
	}
}