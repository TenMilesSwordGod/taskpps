package tui

import (
	"fmt"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	var cmds []tea.Cmd

	s := &m.state
	rec := GetDebugRecorder()
	debugEnabled := rec.IsEnabled()

	if debugEnabled {
		switch msg := msg.(type) {
		case tea.KeyMsg:
			rec.RecordEvent("KEY", fmt.Sprintf("key=%q type=%v alt=%v",
				msg.String(), msg.Type, msg.Alt))
		case tea.WindowSizeMsg:
			rec.RecordEvent("RESIZE", fmt.Sprintf("width=%d height=%d", msg.Width, msg.Height))
		case runsFetchedMsg:
			if msg.err != nil {
				rec.RecordEvent("RUNS_FETCHED", fmt.Sprintf("error=%v", msg.err))
			} else {
				var ids []string
				for _, r := range msg.runs {
					id := r.ID
					if len(id) > 8 {
						id = id[:8]
					}
					ids = append(ids, id)
				}
				rec.RecordEvent("RUNS_FETCHED", fmt.Sprintf("count=%d ids=%v", len(msg.runs), ids))
			}
		case runFetchedMsg:
			if msg.err != nil {
				rec.RecordEvent("RUN_FETCHED", fmt.Sprintf("error=%v", msg.err))
			} else if msg.run != nil {
				idShort := msg.run.ID
				if len(idShort) > 8 {
					idShort = idShort[:8]
				}
				rec.RecordEvent("RUN_FETCHED", fmt.Sprintf("id=%s status=%s tasks=%d",
					idShort, msg.run.Status, len(msg.run.Tasks)))
			}
		case logsFetchedMsg:
			if msg.err != nil {
				rec.RecordEvent("LOGS_FETCHED", fmt.Sprintf("error=%v", msg.err))
			} else {
				var taskNames []string
				for tn := range msg.logs {
					taskNames = append(taskNames, tn)
				}
				rec.RecordEvent("LOGS_FETCHED", fmt.Sprintf("tasks=%d names=%v", len(msg.logs), taskNames))
			}
		case tickMsg:
			rec.RecordEvent("TICK", fmt.Sprintf("focused=%d rightTab=%d pendingRender=%v runs=%d",
				s.FocusedPanel, s.RightTab, m.pendingRender, len(s.Runs)))
		case debounceTickMsg:
			rec.RecordEvent("DEBOUNCE", "render flushed")
		}
	}

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		s.Width = msg.Width
		s.Height = msg.Height
		if !s.Ready {
			s.Ready = true
		}
		m.resizeComponents()

	case tea.KeyMsg:
		m.recordUserActivity()
		switch msg.String() {
		case "q", "ctrl+c":
			s.Quit = true
			return m, tea.Quit

		case "esc":
			oldPanel, oldTab := s.FocusedPanel, s.RightTab
			if s.FocusedPanel == FocusRightPanel {
				m.navigateBack()
			} else {
				s.Quit = true
				return m, tea.Quit
			}
			if debugEnabled {
				rec.RecordEvent("NAV", fmt.Sprintf("esc: focus %d→%d tab %d→%d",
					oldPanel, s.FocusedPanel, oldTab, s.RightTab))
			}

		case "b":
			oldPanel, oldTab := s.FocusedPanel, s.RightTab
			m.navigateBack()
			if debugEnabled {
				rec.RecordEvent("NAV", fmt.Sprintf("back: focus %d→%d tab %d→%d",
					oldPanel, s.FocusedPanel, oldTab, s.RightTab))
			}

		case "tab":
			oldFocus := s.FocusedPanel
			s.FocusedPanel = m.focusNext()
			if debugEnabled {
				rec.RecordEvent("FOCUS", fmt.Sprintf("tab: %d→%d", oldFocus, s.FocusedPanel))
			}

		case "shift+tab":
			oldFocus := s.FocusedPanel
			s.FocusedPanel = m.focusPrev()
			if debugEnabled {
				rec.RecordEvent("FOCUS", fmt.Sprintf("shift+tab: %d→%d", oldFocus, s.FocusedPanel))
			}

		case "t", "T":
			if s.FocusedPanel == FocusRightPanel {
				oldTab := s.RightTab
				s.RightTab = m.cycleTab()
				if debugEnabled {
					rec.RecordEvent("TAB", fmt.Sprintf("cycle: %d→%d", oldTab, s.RightTab))
				}
				if s.RightTab == TabLogs {
					m.runDetail.CollapseAll()
					s.DetailExpanded = make(map[int]bool)
					if m.runDetail.SelectedRun() != nil {
						task := m.runDetail.SelectedTask()
						if task != nil {
							s.LogLoading = true
							m.logViewer.SetLoading(true)
							cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
						}
					}
				}
			}

		case "c":
			if s.FocusedPanel == FocusRightPanel && s.RightTab == TabDetail {
				wasExpanded := m.runDetail.HasExpanded()
				if wasExpanded {
					m.runDetail.CollapseAll()
					s.DetailExpanded = make(map[int]bool)
				} else {
					m.runDetail.ExpandAll()
					s.DetailExpanded = make(map[int]bool)
					if s.SelectedRun != nil {
						for i := range s.SelectedRun.Tasks {
							s.DetailExpanded[i] = true
						}
					}
				}
				if debugEnabled {
					rec.RecordEvent("EXPAND", fmt.Sprintf("c key: was_expanded=%v now_expanded=%v",
						wasExpanded, m.runDetail.HasExpanded()))
				}
			}

		case "p":
			if s.FocusedPanel == FocusRightPanel {
				if prevCmd := m.navigatePrevPipeline(); prevCmd != nil {
					cmds = append(cmds, prevCmd)
				}
				if debugEnabled {
					rec.RecordEvent("PIPELINE", "navigate prev")
				}
			}

		case "n":
			if s.FocusedPanel == FocusRightPanel {
				if nextCmd := m.navigateNextPipeline(); nextCmd != nil {
					cmds = append(cmds, nextCmd)
				}
				if debugEnabled {
					rec.RecordEvent("PIPELINE", "navigate next")
				}
			}

		case "r":
			if debugEnabled {
				rec.RecordEvent("REFRESH", "manual refresh triggered")
			}
			cmds = append(cmds, fetchRuns(m.client))
			if m.runDetail.SelectedRun() != nil {
				cmds = append(cmds, fetchRun(m.client, m.runDetail.SelectedRun().ID))
			}
			return m, tea.Batch(cmds...)

		case "enter":
			if s.FocusedPanel == FocusRunList {
				sel := m.runList.SelectedRun()
				if sel != nil {
					idShort := sel.ID
					if len(idShort) > 8 {
						idShort = idShort[:8]
					}
					if debugEnabled {
						rec.RecordEvent("ENTER", fmt.Sprintf("select run=%s", idShort))
					}
					m.runDetail.SetLoading(true)
					m.runDetail.SetRun(sel)
					s.SelectedRun = sel
					s.LogLoading = false
					s.FocusedPanel = FocusRightPanel
					s.RightTab = TabDetail
					cmds = append(cmds, fetchRun(m.client, sel.ID))
					return m, tea.Batch(cmds...)
				}
			} else if s.FocusedPanel == FocusRightPanel {
				if s.RightTab == TabDetail {
					flatBefore := m.runDetail.FlatCount()
					detailCmd := m.runDetail.Update(msg)
					if debugEnabled && flatBefore != m.runDetail.FlatCount() {
						rec.RecordEvent("EXPAND", fmt.Sprintf("detail toggle: items %d→%d",
							flatBefore, m.runDetail.FlatCount()))
					}
					if detailCmd != nil {
						cmds = append(cmds, detailCmd)
					}
					task := m.runDetail.SelectedTask()
					if task != nil {
						s.SelectedTask = task
						if debugEnabled {
							rec.RecordEvent("ENTER", fmt.Sprintf("expand task=%s", task.TaskName))
						}
						m.runDetail.CollapseAll()
						s.DetailExpanded = make(map[int]bool)
						s.RightTab = TabLogs
						s.LogLoading = true
						cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
					}
				}
			}

		default:
			if debugEnabled {
				rec.RecordEvent("DISPATCH", fmt.Sprintf("key=%q to panel=%d tab=%d",
					msg.String(), s.FocusedPanel, s.RightTab))
			}
			cmd = m.dispatchKey(msg)
			if cmd != nil {
				cmds = append(cmds, cmd)
			}
		}

	case runsFetchedMsg:
		if msg.err != nil {
			s.ErrorMsg = msg.err.Error()
			return m, nil
		}

		newHash := computeRunsHash(msg.runs)
		if newHash == s.RunsHash {
			if debugEnabled {
				oldShort := s.RunsHash
				newShort := newHash
				if len(oldShort) > 12 {
					oldShort = oldShort[:12]
				}
				if len(newShort) > 12 {
					newShort = newShort[:12]
				}
				rec.RecordEvent("HASH", fmt.Sprintf("runs unchanged old=%s new=%s", oldShort, newShort))
			}
			return m, nil
		}
		if debugEnabled {
			oldShort := s.RunsHash
			newShort := newHash
			if len(oldShort) > 12 {
				oldShort = oldShort[:12]
			}
			if len(newShort) > 12 {
				newShort = newShort[:12]
			}
			rec.RecordEvent("HASH", fmt.Sprintf("runs changed old=%s new=%s", oldShort, newShort))
		}
		s.RunsHash = newHash
		s.ErrorMsg = ""
		beforeCount := len(s.Runs)
		s.Runs = mergeRuns(s.Runs, msg.runs)
		if debugEnabled {
			rec.RecordEvent("MERGE", fmt.Sprintf("runs: before=%d fetched=%d merged=%d",
				beforeCount, len(msg.runs), len(s.Runs)))
		}
		m.runList.SetRuns(s.Runs)

		if m.targetRunID != "" {
			for i, r := range s.Runs {
				if r.ID == m.targetRunID {
					m.runList.SetCursor(i)
					s.RunListCursor = i
					m.runDetail.SetRun(&s.Runs[i])
					s.SelectedRun = &s.Runs[i]
					s.FocusedPanel = FocusRightPanel
					s.RightTab = TabDetail
					cmds = append(cmds, fetchRun(m.client, r.ID))
					m.targetRunID = ""
					break
				}
			}
		}

		if !m.pendingRender {
			m.pendingRender = true
			if debugEnabled {
				rec.RecordEvent("DEBOUNCE", "pendingRender=true -> scheduling debounce tick")
			}
			cmds = append(cmds, tea.Tick(debounceInterval, func(_ time.Time) tea.Msg {
				return debounceTickMsg{}
			}))
		}

	case runFetchedMsg:
		if msg.err != nil {
			s.ErrorMsg = msg.err.Error()
			m.runDetail.SetLoading(false)
			return m, nil
		}

		newHash := computeRunHash(msg.run)
		if newHash == s.RunHash {
			if debugEnabled {
				oldShort := s.RunHash
				newShort := newHash
				if len(oldShort) > 12 {
					oldShort = oldShort[:12]
				}
				if len(newShort) > 12 {
					newShort = newShort[:12]
				}
				rec.RecordEvent("HASH", fmt.Sprintf("run unchanged old=%s new=%s", oldShort, newShort))
			}
			return m, nil
		}
		if debugEnabled {
			oldShort := s.RunHash
			newShort := newHash
			if len(oldShort) > 12 {
				oldShort = oldShort[:12]
			}
			if len(newShort) > 12 {
				newShort = newShort[:12]
			}
			rec.RecordEvent("HASH", fmt.Sprintf("run changed old=%s new=%s", oldShort, newShort))
		}
		s.RunHash = newHash
		s.ErrorMsg = ""
		m.runDetail.SetLoading(false)
		m.runDetail.SetRun(msg.run)
		if msg.run != nil {
			s.SelectedRun = msg.run
			for i, r := range s.Runs {
				if r.ID == msg.run.ID {
					s.Runs[i] = *msg.run
					break
				}
			}
			m.runList.SetRuns(s.Runs)
		}

		if !m.pendingRender {
			m.pendingRender = true
			if debugEnabled {
				rec.RecordEvent("DEBOUNCE", "pendingRender=true (runFetchedMsg)")
			}
			cmds = append(cmds, tea.Tick(debounceInterval, func(_ time.Time) tea.Msg {
				return debounceTickMsg{}
			}))
		}

	case logsFetchedMsg:
		if msg.err != nil {
			s.ErrorMsg = msg.err.Error()
			m.logViewer.SetLoading(false)
			m.logViewer.SetContent(components.ErrorStyle.Render("Error: ") + msg.err.Error())
			s.LogLoading = false
			s.LogContent = components.ErrorStyle.Render("Error: ") + msg.err.Error()
		} else {
			s.ErrorMsg = ""
			m.logViewer.SetLoading(false)
			s.LogLoading = false
			var content string
			for taskName, log := range msg.logs {
				content += components.LabelStyle.Render("["+taskName+"]") + "\n" + log + "\n"
			}
			m.logViewer.SetContent(content)
			s.LogContent = content
		}

		if !m.pendingRender {
			m.pendingRender = true
			if debugEnabled {
				rec.RecordEvent("DEBOUNCE", "pendingRender=true (logsFetchedMsg)")
			}
			cmds = append(cmds, tea.Tick(debounceInterval, func(_ time.Time) tea.Msg {
				return debounceTickMsg{}
			}))
		}

	case tickMsg:
		if m.shouldSkipTick() {
			if debugEnabled {
				rec.RecordEvent("TICK", "skipped: user activity cooldown")
			}
			cmds = append(cmds, tea.Tick(time.Duration(refreshInterval)*time.Second, func(_ time.Time) tea.Msg {
				return tickMsg{}
			}))
			break
		}

		cmds = append(cmds, fetchRuns(m.client))
		sel := m.runDetail.SelectedRun()
		if sel != nil {
			cmds = append(cmds, fetchRun(m.client, sel.ID))
			if s.RightTab == TabLogs {
				task := m.runDetail.SelectedTask()
				if task != nil && task.Status == models.TaskStatusRunning {
					cmds = append(cmds, fetchLogs(m.client, sel.ID, task.TaskName))
				}
			}
		}
		if debugEnabled {
			rec.RecordEvent("TICK", fmt.Sprintf("active: fetching runs+run%s",
				map[bool]string{true: "+logs", false: ""}[s.RightTab == TabLogs]))
		}
		cmds = append(cmds, tea.Tick(time.Duration(refreshInterval)*time.Second, func(_ time.Time) tea.Msg {
			return tickMsg{}
		}))

	case debounceTickMsg:
		m.pendingRender = false
		if debugEnabled {
			rec.RecordEvent("DEBOUNCE", "pendingRender=false -> render flushed to terminal")
		}
		return m, nil
	}

	if len(cmds) > 0 {
		return m, tea.Batch(cmds...)
	}
	return m, cmd
}

func (m *Model) dispatchKey(msg tea.KeyMsg) tea.Cmd {
	rec := GetDebugRecorder()
	debugEnabled := rec.IsEnabled()
	s := &m.state

	switch s.FocusedPanel {
	case FocusRunList:
		var cmd tea.Cmd
		oldCursor := m.runList.Cursor()
		m.runList, cmd = m.runList.Update(msg)
		s.RunListCursor = m.runList.Cursor()
		if debugEnabled && oldCursor != m.runList.Cursor() {
			rec.RecordEvent("CURSOR", fmt.Sprintf("runlist: %d→%d total=%d",
				oldCursor, m.runList.Cursor(), m.runList.Len()))
		}
		return cmd
	case FocusRightPanel:
		if s.RightTab == TabDetail {
			oldCursor := m.runDetail.Cursor()
			detailCmd := m.runDetail.Update(msg)
			s.DetailCursor = m.runDetail.Cursor()
			if debugEnabled && oldCursor != m.runDetail.Cursor() {
				rec.RecordEvent("CURSOR", fmt.Sprintf("detail: %d→%d items=%d",
					oldCursor, m.runDetail.Cursor(), m.runDetail.FlatCount()))
			}
			if detailCmd != nil {
				return detailCmd
			}
			run := m.runDetail.SelectedRun()
			task := m.runDetail.SelectedTask()
			if run != nil && task != nil && s.RightTab == TabDetail && !m.logViewer.IsLoading() {
				s.SelectedTask = task
				preFetchLogs := func() tea.Msg {
					logs, err := fetchLogsSync(m.client, run.ID, task.TaskName)
					if err != nil {
						return logsFetchedMsg{logs: nil, err: err}
					}
					return logsFetchedMsg{logs: logs, err: nil}
				}
				return preFetchLogs
			}
			return nil
		}
		return m.logViewer.Update(msg)
	}
	return nil
}

func (m *Model) resizeComponents() {
	s := &m.state
	headerH := 1
	footerH := 1
	availableH := s.Height - headerH - footerH
	if availableH < 5 {
		availableH = 5
	}

	borderH := 2
	borderW := 2
	manualPadW := 2
	dividerW := 1

	contentH := availableH - borderH
	if contentH < 3 {
		contentH = 3
	}

	innerW := s.Width - borderW
	totalContentW := innerW - manualPadW - dividerW
	if totalContentW < 36 {
		totalContentW = 36
		innerW = totalContentW + manualPadW + dividerW
	}

	leftContentW := totalContentW * 28 / 100
	rightContentW := totalContentW - leftContentW
	if leftContentW < 14 {
		leftContentW = 14
		rightContentW = totalContentW - leftContentW
	}
	if rightContentW < 20 {
		rightContentW = 20
		leftContentW = totalContentW - rightContentW
		if leftContentW < 14 {
			leftContentW = 14
		}
	}

	s.Dims = layoutDims{
		innerW:        innerW,
		leftContentW:  leftContentW,
		rightContentW: rightContentW,
		panelH:        availableH,
		contentH:      contentH,
	}

	m.runList.SetSize(leftContentW, contentH)
	m.runDetail.SetSize(rightContentW, contentH)
	m.logViewer.SetSize(rightContentW, contentH)
}

func mergeRuns(existing []models.Run, newRuns []models.Run) []models.Run {
	existingMap := make(map[string]models.Run)
	for _, r := range existing {
		existingMap[r.ID] = r
	}

	result := make([]models.Run, 0, len(newRuns))
	for _, r := range newRuns {
		if e, ok := existingMap[r.ID]; ok {
			if len(e.Tasks) > 0 {
				r.Tasks = e.Tasks
			}
		}
		result = append(result, r)
	}
	return result
}