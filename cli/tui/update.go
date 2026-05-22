package tui

import (
	"fmt"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
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
		case "q", "esc", "ctrl+c":
			m.quit = true
			return m, tea.Quit

		case "tab":
			m.focusedPanel = m.focusNext()

		case "shift+tab":
			m.focusedPanel = m.focusPrev()

		case "right", "l":
			if m.focusedPanel == FocusRunList {
				m.focusedPanel = FocusRunDetail
			}

		case "left", "h":
			if m.focusedPanel == FocusRunDetail {
				m.focusedPanel = FocusRunList
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
					m.focusedPanel = FocusRunDetail
					cmds = append(cmds, fetchRun(m.client, sel.ID))
				}
			} else if m.focusedPanel == FocusRunDetail {
				var detailCmd tea.Cmd
				m.runDetail, detailCmd = m.runDetail.Update(msg)
				if detailCmd != nil {
					cmds = append(cmds, detailCmd)
				}
				task := m.runDetail.SelectedTask()
				if task != nil {
					cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
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
			m.runs = msg.runs
			m.runList.SetRuns(msg.runs)

			if m.targetRunID != "" {
				for i, r := range msg.runs {
					if r.ID == m.targetRunID {
						m.runList.SetCursor(i)
						m.runDetail.SetRun(&msg.runs[i])
						m.focusedPanel = FocusRunDetail
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
		}

	case logsFetchedMsg:
		if msg.err != nil {
			m.errMsg = msg.err.Error()
			m.logViewer.SetContent("Error: " + msg.err.Error())
		} else {
			m.errMsg = ""
			var content string
			for taskName, log := range msg.logs {
				content += "[" + taskName + "]\n" + log + "\n"
			}
			m.logViewer.SetContent(content)
		}

	case tickMsg:
		cmds = append(cmds, fetchRuns(m.client))
		sel := m.runDetail.SelectedRun()
		if sel != nil {
			cmds = append(cmds, fetchRun(m.client, sel.ID))
		}
		cmds = append(cmds, tea.Tick(2*time.Second, func(_ time.Time) tea.Msg {
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
	case FocusRunDetail:
		var cmd tea.Cmd
		m.runDetail, cmd = m.runDetail.Update(msg)
		return cmd
	case FocusLogViewer:
		var cmd tea.Cmd
		m.logViewer, cmd = m.logViewer.Update(msg)
		return cmd
	}
	return nil
}

func (m *Model) resizeComponents() {
	// Calculate available height properly
	header := renderHeader(m.width)
	footer := renderFooter(m.width, *m)
	
	errLine := ""
	if m.errMsg != "" {
		errLine = components.ErrorStyle.Render(fmt.Sprintf(" ERROR: %s ", m.errMsg))
	}

	headerH := lipgloss.Height(header)
	footerH := lipgloss.Height(footer)
	errH := lipgloss.Height(errLine)
	availableH := m.height - headerH - footerH - errH
	if availableH < 5 {
		availableH = 5
	}

	w := m.width
	h := availableH

	listW := w * 25 / 100
	detailW := w * 35 / 100
	logW := w - listW - detailW - 6 // 6 = 2*3 for borders

	if listW < 15 {
		listW = 15
	}
	if detailW < 20 {
		detailW = 20
	}
	if logW < 20 {
		logW = 20
	}

	// Components get internal width (panel width minus borders)
	m.runList.SetSize(listW-2, h-2)
	m.runDetail.SetSize(detailW-2, h-2)
	m.logViewer.SetSize(logW-2, h-2)
}