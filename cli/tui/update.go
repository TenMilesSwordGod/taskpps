package tui

import (
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		if !m.ready {
			m.ready = true
		}
		m.resizeComponents()

	case tea.KeyMsg:
		switch msg.String() {
		case "q", "ctrl+c":
			m.quit = true
			return m, tea.Quit

		case "esc":
			if m.focusedPanel == FocusRightPanel {
				m.navigateBack()
			} else {
				m.quit = true
				return m, tea.Quit
			}

		case "b":
			m.navigateBack()

		case "tab":
			m.focusedPanel = m.focusNext()

		case "shift+tab":
			m.focusedPanel = m.focusPrev()

		case "t", "T":
			if m.focusedPanel == FocusRightPanel {
				m.rightTab = m.cycleTab()
				if m.rightTab == TabLogs {
					m.runDetail.CollapseAll()
					if m.runDetail.SelectedRun() != nil {
						task := m.runDetail.SelectedTask()
						if task != nil {
							cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
						}
					}
				}
			}

		case "c":
			if m.focusedPanel == FocusRightPanel && m.rightTab == TabDetail {
				if m.runDetail.HasExpanded() {
					m.runDetail.CollapseAll()
				} else {
					m.runDetail.ExpandAll()
				}
			}

		case "p":
			if m.focusedPanel == FocusRightPanel {
				if prevCmd := m.navigatePrevPipeline(); prevCmd != nil {
					cmds = append(cmds, prevCmd)
				}
			}

		case "n":
			if m.focusedPanel == FocusRightPanel {
				if nextCmd := m.navigateNextPipeline(); nextCmd != nil {
					cmds = append(cmds, nextCmd)
				}
			}

		case "r":
			cmds = append(cmds, fetchRuns(m.client))
			if m.runDetail.SelectedRun() != nil {
				cmds = append(cmds, fetchRun(m.client, m.runDetail.SelectedRun().ID))
			}
			return m, tea.Batch(cmds...)

		case "enter":
			if m.focusedPanel == FocusRunList {
				sel := m.runList.SelectedRun()
				if sel != nil {
					m.runDetail.SetRun(sel)
					m.focusedPanel = FocusRightPanel
					m.rightTab = TabDetail
					cmds = append(cmds, fetchRun(m.client, sel.ID))
				}
			} else if m.focusedPanel == FocusRightPanel {
				if m.rightTab == TabDetail {
					detailCmd := m.runDetail.Update(msg)
					if detailCmd != nil {
						cmds = append(cmds, detailCmd)
					}
					task := m.runDetail.SelectedTask()
					if task != nil {
						m.runDetail.CollapseAll()
						m.rightTab = TabLogs
						cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
					}
				}
			}

		default:
			cmd = m.dispatchKey(msg)
			if cmd != nil {
				cmds = append(cmds, cmd)
			}
		}

	case runsFetchedMsg:
		if msg.err != nil {
			m.errMsg = msg.err.Error()
		} else {
			m.errMsg = ""
			m.runs = mergeRuns(m.runs, msg.runs)
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
		}

	case runFetchedMsg:
		if msg.err != nil {
			m.errMsg = msg.err.Error()
		} else {
			m.errMsg = ""
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
		}

	case logsFetchedMsg:
		if msg.err != nil {
			m.errMsg = msg.err.Error()
			m.logViewer.SetContent(components.ErrorStyle.Render("Error: ") + msg.err.Error())
		} else {
			m.errMsg = ""
			var content string
			for taskName, log := range msg.logs {
				content += components.LabelStyle.Render("["+taskName+"]") + "\n" + log + "\n"
			}
			m.logViewer.SetContent(content)
		}

	case tickMsg:
		cmds = append(cmds, fetchRuns(m.client))
		sel := m.runDetail.SelectedRun()
		if sel != nil {
			cmds = append(cmds, fetchRun(m.client, sel.ID))
			if m.rightTab == TabLogs {
				task := m.runDetail.SelectedTask()
				if task != nil {
					cmds = append(cmds, fetchLogs(m.client, sel.ID, task.TaskName))
				}
			}
		}
		cmds = append(cmds, tea.Tick(time.Duration(refreshInterval)*time.Second, func(_ time.Time) tea.Msg {
			return tickMsg{}
		}))
	}

	if len(cmds) > 0 {
		return m, tea.Batch(cmds...)
	}
	return m, cmd
}

func (m *Model) dispatchKey(msg tea.KeyMsg) tea.Cmd {
	switch m.focusedPanel {
	case FocusRunList:
		var cmd tea.Cmd
		m.runList, cmd = m.runList.Update(msg)
		return cmd
	case FocusRightPanel:
		if m.rightTab == TabDetail {
			return m.runDetail.Update(msg)
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

	m.runList.SetSize(leftContentW, contentH-1)
	m.runDetail.SetSize(rightContentW, contentH-1)
	m.logViewer.SetSize(rightContentW, contentH-1)
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
