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

		case "t", "T":
			// Cycle between Detail and Logs tabs when right panel is focused
			if m.focusedPanel == FocusRightPanel {
				m.rightTab = m.cycleTab()
				if m.rightTab == TabLogs && m.runDetail.SelectedRun() != nil {
					task := m.runDetail.SelectedTask()
					if task != nil {
						cmds = append(cmds, fetchLogs(m.client, m.runDetail.SelectedRun().ID, task.TaskName))
					}
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
			m.runs = msg.runs
			m.runList.SetRuns(msg.runs)

			if m.targetRunID != "" {
				for i, r := range msg.runs {
					if r.ID == m.targetRunID {
						m.runList.SetCursor(i)
						m.runDetail.SetRun(&msg.runs[i])
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
			if m.rightTab == TabLogs {
				task := m.runDetail.SelectedTask()
				if task != nil {
					cmds = append(cmds, fetchLogs(m.client, sel.ID, task.TaskName))
				}
			}
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
	case FocusRightPanel:
		if m.rightTab == TabDetail {
			return m.runDetail.Update(msg)
		} else {
			return m.logViewer.Update(msg)
		}
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

	// Panel border (1 each side) + padding (1 each side) = 4 total
	panelFrameW := 4
	panelFrameH := 4
	gap := 2
	// Right panel has tabs which take 1 line + 1 newline
	rightTabH := 2

	// 2-panel layout: left (run list) + right (detail/logs)
	// Available width for both panels' content + frames + gap
	contentW := w - panelFrameW - gap - panelFrameW
	leftContentW := contentW * 20 / 100
	rightContentW := contentW - leftContentW

	if leftContentW < 16 {
		leftContentW = 16
	}
	if rightContentW < 26 {
		rightContentW = 26
	}

	// Component sizes = content area inside panel (panel total - frame)
	// For height: panel has frame on top/bottom, and right panel also has tabs
	m.runList.SetSize(leftContentW, h-panelFrameH)
	m.runDetail.SetSize(rightContentW, h-panelFrameH-rightTabH)
	m.logViewer.SetSize(rightContentW, h-panelFrameH-rightTabH)
}
