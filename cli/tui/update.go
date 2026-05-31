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
				m.focusedPanel, m.rightTab, m.pendingRender, len(m.runs)))
		case debounceTickMsg:
			rec.RecordEvent("DEBOUNCE", "render flushed")
		}
	}

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		if !m.ready {
			m.ready = true
		}
		m.resizeComponents()

	case tea.KeyMsg:
		m.recordUserActivity()
		switch msg.String() {
		case "q", "ctrl+c":
			m.quit = true
			return m, tea.Quit

		case "esc":
			oldPanel, oldTab := m.focusedPanel, m.rightTab
			if m.focusedPanel == FocusRightPanel {
				m.navigateBack()
			} else {
				m.quit = true
				return m, tea.Quit
			}
			if debugEnabled {
				rec.RecordEvent("NAV", fmt.Sprintf("esc: focus %d→%d tab %d→%d",
					oldPanel, m.focusedPanel, oldTab, m.rightTab))
			}

		case "b":
			oldPanel, oldTab := m.focusedPanel, m.rightTab
			m.navigateBack()
			if debugEnabled {
				rec.RecordEvent("NAV", fmt.Sprintf("back: focus %d→%d tab %d→%d",
					oldPanel, m.focusedPanel, oldTab, m.rightTab))
			}

		case "tab":
			oldFocus := m.focusedPanel
			m.focusedPanel = m.focusNext()
			if debugEnabled {
				rec.RecordEvent("FOCUS", fmt.Sprintf("tab: %d→%d", oldFocus, m.focusedPanel))
			}

		case "shift+tab":
			oldFocus := m.focusedPanel
			m.focusedPanel = m.focusPrev()
			if debugEnabled {
				rec.RecordEvent("FOCUS", fmt.Sprintf("shift+tab: %d→%d", oldFocus, m.focusedPanel))
			}

		case "t", "T":
			if m.focusedPanel == FocusRightPanel {
				oldTab := m.rightTab
				m.rightTab = m.cycleTab()
				if debugEnabled {
					rec.RecordEvent("TAB", fmt.Sprintf("cycle: %d→%d", oldTab, m.rightTab))
				}
				if m.rightTab == TabLogs {
					m.runDetail.CollapseAll()
					if m.runDetail.SelectedRun() != nil {
						task := m.runDetail.SelectedTask()
						if task != nil {
							m.logViewer.SetLoading(true)
							cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
						}
					}
				}
			}

		case "c":
			if m.focusedPanel == FocusRightPanel && m.rightTab == TabDetail {
				wasExpanded := m.runDetail.HasExpanded()
				if wasExpanded {
					m.runDetail.CollapseAll()
				} else {
					m.runDetail.ExpandAll()
				}
				if debugEnabled {
					rec.RecordEvent("EXPAND", fmt.Sprintf("c key: was_expanded=%v now_expanded=%v",
						wasExpanded, m.runDetail.HasExpanded()))
				}
			}

		case "p":
			if m.focusedPanel == FocusRightPanel {
				if prevCmd := m.navigatePrevPipeline(); prevCmd != nil {
					cmds = append(cmds, prevCmd)
				}
				if debugEnabled {
					rec.RecordEvent("PIPELINE", "navigate prev")
				}
			}

		case "n":
			if m.focusedPanel == FocusRightPanel {
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
			if m.focusedPanel == FocusRunList {
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
					m.focusedPanel = FocusRightPanel
					m.rightTab = TabDetail
					cmds = append(cmds, fetchRun(m.client, sel.ID))
					return m, tea.Batch(cmds...)
				}
			} else if m.focusedPanel == FocusRightPanel {
				if m.rightTab == TabDetail {
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
						if debugEnabled {
							rec.RecordEvent("ENTER", fmt.Sprintf("expand task=%s", task.TaskName))
						}
						m.runDetail.CollapseAll()
						m.rightTab = TabLogs
						cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
					}
				}
			}

		default:
			if debugEnabled {
				rec.RecordEvent("DISPATCH", fmt.Sprintf("key=%q to panel=%d tab=%d",
					msg.String(), m.focusedPanel, m.rightTab))
			}
			cmd = m.dispatchKey(msg)
			if cmd != nil {
				cmds = append(cmds, cmd)
			}
		}

	case runsFetchedMsg:
		if msg.err != nil {
			m.errMsg = msg.err.Error()
			return m, nil
		}

		newHash := computeRunsHash(msg.runs)
		if newHash == m.runsHash {
			if debugEnabled {
				oldShort := m.runsHash
				newShort := newHash
				if len(oldShort) > 12 { oldShort = oldShort[:12] }
				if len(newShort) > 12 { newShort = newShort[:12] }
				rec.RecordEvent("HASH", fmt.Sprintf("runs unchanged old=%s new=%s", oldShort, newShort))
			}
			return m, nil
		}
		if debugEnabled {
			oldShort := m.runsHash
			newShort := newHash
			if len(oldShort) > 12 { oldShort = oldShort[:12] }
			if len(newShort) > 12 { newShort = newShort[:12] }
			rec.RecordEvent("HASH", fmt.Sprintf("runs changed old=%s new=%s", oldShort, newShort))
		}
		m.runsHash = newHash
		m.errMsg = ""
		beforeCount := len(m.runs)
		m.runs = mergeRuns(m.runs, msg.runs)
		if debugEnabled {
			rec.RecordEvent("MERGE", fmt.Sprintf("runs: before=%d fetched=%d merged=%d",
				beforeCount, len(msg.runs), len(m.runs)))
		}
		m.runList.SetRuns(m.runs)

		if m.targetRunID != "" {
			for i, r := range m.runs {
				if r.ID == m.targetRunID {
					m.runList.SetCursor(i)
					m.runDetail.SetRun(&m.runs[i])
					m.focusedPanel = FocusRightPanel
					m.rightTab = TabDetail
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
			m.errMsg = msg.err.Error()
			m.runDetail.SetLoading(false)
			return m, nil
		}

		newHash := computeRunHash(msg.run)
		if newHash == m.runHash {
			if debugEnabled {
				oldShort := m.runHash
				newShort := newHash
				if len(oldShort) > 12 { oldShort = oldShort[:12] }
				if len(newShort) > 12 { newShort = newShort[:12] }
				rec.RecordEvent("HASH", fmt.Sprintf("run unchanged old=%s new=%s", oldShort, newShort))
			}
			return m, nil
		}
		if debugEnabled {
			oldShort := m.runHash
			newShort := newHash
			if len(oldShort) > 12 { oldShort = oldShort[:12] }
			if len(newShort) > 12 { newShort = newShort[:12] }
			rec.RecordEvent("HASH", fmt.Sprintf("run changed old=%s new=%s", oldShort, newShort))
		}
		m.runHash = newHash
		m.errMsg = ""
		m.runDetail.SetLoading(false)
		m.runDetail.SetRun(msg.run)
		if msg.run != nil {
			for i, r := range m.runs {
				if r.ID == msg.run.ID {
					m.runs[i] = *msg.run
					break
				}
			}
			m.runList.SetRuns(m.runs)
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
			m.errMsg = msg.err.Error()
			m.logViewer.SetLoading(false)
			m.logViewer.SetContent(components.ErrorStyle.Render("Error: ") + msg.err.Error())
		} else {
			m.errMsg = ""
			m.logViewer.SetLoading(false)
			var content string
			for taskName, log := range msg.logs {
				content += components.LabelStyle.Render("["+taskName+"]") + "\n" + log + "\n"
			}
			m.logViewer.SetContent(content)
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
			if m.rightTab == TabLogs {
				task := m.runDetail.SelectedTask()
				if task != nil && task.Status == models.TaskStatusRunning {
					cmds = append(cmds, fetchLogs(m.client, sel.ID, task.TaskName))
				}
			}
		}
		if debugEnabled {
			rec.RecordEvent("TICK", fmt.Sprintf("active: fetching runs+run%s",
				map[bool]string{true: "+logs", false: ""}[m.rightTab == TabLogs]))
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

	switch m.focusedPanel {
	case FocusRunList:
		var cmd tea.Cmd
		oldCursor := m.runList.Cursor()
		m.runList, cmd = m.runList.Update(msg)
		if debugEnabled && oldCursor != m.runList.Cursor() {
			rec.RecordEvent("CURSOR", fmt.Sprintf("runlist: %d→%d total=%d",
				oldCursor, m.runList.Cursor(), m.runList.Len()))
		}
		return cmd
	case FocusRightPanel:
		if m.rightTab == TabDetail {
			oldCursor := m.runDetail.Cursor()
			detailCmd := m.runDetail.Update(msg)
			if debugEnabled && oldCursor != m.runDetail.Cursor() {
				rec.RecordEvent("CURSOR", fmt.Sprintf("detail: %d→%d items=%d",
					oldCursor, m.runDetail.Cursor(), m.runDetail.FlatCount()))
			}
			if detailCmd != nil {
				return detailCmd
			}
			run := m.runDetail.SelectedRun()
			task := m.runDetail.SelectedTask()
			if run != nil && task != nil && m.rightTab == TabDetail && !m.logViewer.IsLoading() {
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
	headerH := 1
	footerH := 1
	availableH := m.height - headerH - footerH
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

	innerW := m.width - borderW
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

	m.dims = layoutDims{
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
