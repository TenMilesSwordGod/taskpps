package components

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/taskpps/ppsctl/models"
)

type subpipelineGroup struct {
	name  string
	tasks []int
}

type RunDetailModel struct {
	run       *models.Run
	cursor    int
	expanded  map[int]bool
	subExpanded map[string]bool
	width     int
	height    int
	viewport  viewport.Model
	ready     bool
	groups    []subpipelineGroup
	flatItems []flatItem
}

type flatItem struct {
	kind       string
	subName    string
	taskIdx    int
}

func NewRunDetailModel() RunDetailModel {
	return RunDetailModel{
		expanded:    make(map[int]bool),
		subExpanded: make(map[string]bool),
	}
}

func (m *RunDetailModel) buildGroups() {
	if m.run == nil {
		m.groups = nil
		m.flatItems = nil
		return
	}

	groupMap := make(map[string][]int)
	order := []string{}
	for i, t := range m.run.Tasks {
		name := t.SubpipelineName
		if name == "" {
			name = "default"
		}
		if _, ok := groupMap[name]; !ok {
			order = append(order, name)
		}
		groupMap[name] = append(groupMap[name], i)
	}

	m.groups = make([]subpipelineGroup, 0, len(order))
	for _, name := range order {
		m.groups = append(m.groups, subpipelineGroup{name: name, tasks: groupMap[name]})
	}

	m.flatItems = nil
	for _, g := range m.groups {
		m.flatItems = append(m.flatItems, flatItem{kind: "sub", subName: g.name})
		for _, idx := range g.tasks {
			m.flatItems = append(m.flatItems, flatItem{kind: "task", taskIdx: idx, subName: g.name})
		}
	}
}

func (m *RunDetailModel) SetRun(run *models.Run) {
	m.run = run
	m.buildGroups()
	if run != nil {
		for _, g := range m.groups {
			m.subExpanded[g.name] = true
		}
		m.rebuildFlatItems()
		if m.cursor >= len(m.flatItems) && len(m.flatItems) > 0 {
			m.cursor = len(m.flatItems) - 1
		}
	}
	if m.ready {
		m.updateViewportContent()
	}
}

func (m *RunDetailModel) SetSize(w, h int) {
	m.width = w
	m.height = h
	if !m.ready {
		m.viewport = viewport.New(w, h)
		m.viewport.YPosition = 0
		m.viewport.Style = lipgloss.NewStyle()
		m.ready = true
	} else {
		m.viewport.Width = w
		m.viewport.Height = h
	}
	m.updateViewportContent()
}

func (m *RunDetailModel) SelectedRun() *models.Run {
	return m.run
}

func (m *RunDetailModel) SetCursor(idx int) {
	if idx >= 0 && idx < len(m.flatItems) {
		m.cursor = idx
	}
}

func (m *RunDetailModel) SelectedTask() *models.TaskRun {
	if m.run == nil || len(m.flatItems) == 0 || m.cursor >= len(m.flatItems) {
		return nil
	}
	item := m.flatItems[m.cursor]
	if item.kind != "task" {
		return nil
	}
	if item.taskIdx >= len(m.run.Tasks) {
		return nil
	}
	return &m.run.Tasks[item.taskIdx]
}

func (m *RunDetailModel) Update(msg tea.Msg) tea.Cmd {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
				m.skipCollapsedTasks()
				m.updateViewportContent()
			} else {
				m.viewport, cmd = m.viewport.Update(msg)
			}
		case "down", "j":
			if m.cursor < len(m.flatItems)-1 {
				m.cursor++
				m.skipCollapsedTasks()
				m.updateViewportContent()
			} else {
				m.viewport, cmd = m.viewport.Update(msg)
			}
		case "enter":
			if m.cursor < len(m.flatItems) {
				item := m.flatItems[m.cursor]
				if item.kind == "sub" {
					m.subExpanded[item.subName] = !m.subExpanded[item.subName]
					m.rebuildFlatItems()
				} else {
					m.expanded[item.taskIdx] = !m.expanded[item.taskIdx]
				}
				m.updateViewportContent()
			}
		default:
			m.viewport, cmd = m.viewport.Update(msg)
		}
	default:
		m.viewport, cmd = m.viewport.Update(msg)
	}
	return cmd
}

func (m *RunDetailModel) skipCollapsedTasks() {
	for m.cursor < len(m.flatItems) {
		item := m.flatItems[m.cursor]
		if item.kind == "sub" {
			break
		}
		parentExpanded := m.subExpanded[item.subName]
		if parentExpanded {
			break
		}
		m.cursor++
	}
	if m.cursor >= len(m.flatItems) && len(m.flatItems) > 0 {
		m.cursor = len(m.flatItems) - 1
	}
}

func (m *RunDetailModel) rebuildFlatItems() {
	m.flatItems = nil
	for _, g := range m.groups {
		m.flatItems = append(m.flatItems, flatItem{kind: "sub", subName: g.name})
		if m.subExpanded[g.name] {
			for _, idx := range g.tasks {
				m.flatItems = append(m.flatItems, flatItem{kind: "task", taskIdx: idx, subName: g.name})
			}
		}
	}
	if m.cursor >= len(m.flatItems) && len(m.flatItems) > 0 {
		m.cursor = len(m.flatItems) - 1
	}
}

func (m *RunDetailModel) updateViewportContent() {
	var b strings.Builder

	if m.run == nil {
		b.WriteString("\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(select a run)"))
		b.WriteString("\n")
	} else {
		b.WriteString(TruncateLine(fmt.Sprintf("ID: %s", m.run.ID), m.width))
		b.WriteString("\n")
		b.WriteString(TruncateLine(fmt.Sprintf("Pipeline: %s", m.run.PipelineName), m.width))
		b.WriteString("\n")

		statusStyle := StatusStyle(string(m.run.Status))
		b.WriteString(TruncateLine(fmt.Sprintf("Status: %s", statusStyle.Render(string(m.run.Status))), m.width))
		b.WriteString("\n")

		if m.run.StartedAt != nil {
			b.WriteString(TruncateLine(fmt.Sprintf("Started: %s", *m.run.StartedAt), m.width))
			b.WriteString("\n")
		}
		if m.run.FinishedAt != nil {
			b.WriteString(TruncateLine(fmt.Sprintf("Finished: %s", *m.run.FinishedAt), m.width))
			b.WriteString("\n")
		}
		b.WriteString("\n")

		if len(m.run.Tasks) == 0 {
			b.WriteString("  (no tasks)\n")
		} else {
			cursorIdx := 0
			for _, g := range m.groups {
				isExpanded := m.subExpanded[g.name]
				expandIcon := "▶ "
				if isExpanded {
					expandIcon = "▼ "
				}

				isCursor := cursorIdx < len(m.flatItems) && m.cursor == cursorIdx
				prefix := "  "
				if isCursor {
					prefix = CursorStyle.Render("> ")
				}

				subLine := fmt.Sprintf("%s%s%s %s (%d tasks)",
					prefix, expandIcon,
					SubpipelineStyle.Render(g.name),
					SubpipelineStyle.Render("pipeline"),
					len(g.tasks))

				b.WriteString(TruncateLine(subLine, m.width))
				b.WriteString("\n")
				cursorIdx++

				if isExpanded {
					for ti, taskIdx := range g.tasks {
						task := m.run.Tasks[taskIdx]
						icon := StatusIcon(string(task.Status))
						style := StatusStyle(string(task.Status))

						connector := TreeBranch + " "
						if ti == len(g.tasks)-1 {
							connector = TreeLast + " "
						}

						taskExpandIcon := "  "
						if m.expanded[taskIdx] {
							taskExpandIcon = "▼ "
						}

						isTaskCursor := cursorIdx < len(m.flatItems) && m.cursor == cursorIdx
						taskPrefix := "  " + connector + taskExpandIcon
						if isTaskCursor {
							taskPrefix = "  " + connector + CursorStyle.Render("> ")
						}

						displayName := task.TaskName
						if strings.HasPrefix(displayName, g.name+".") {
							displayName = displayName[len(g.name)+1:]
						}

						line := fmt.Sprintf("%s%s %s  %s", taskPrefix, icon, displayName, style.Render(string(task.Status)))
						if task.ExitCode != nil {
							line += fmt.Sprintf(" (exit: %d)", *task.ExitCode)
						}

						b.WriteString(TruncateLine(line, m.width))
						b.WriteString("\n")

						if m.expanded[taskIdx] {
							indent := "  "
							if ti == len(g.tasks)-1 {
								indent = "    "
							} else {
								indent = "  " + TreeConnector
							}

							b.WriteString(TruncateLine(fmt.Sprintf("%s  Type: %s", indent, task.TaskType), m.width))
							b.WriteString("\n")
							if task.StartedAt != nil {
								b.WriteString(TruncateLine(fmt.Sprintf("%s  Started: %s", indent, *task.StartedAt), m.width))
								b.WriteString("\n")
							}
							if task.FinishedAt != nil {
								b.WriteString(TruncateLine(fmt.Sprintf("%s  Finished: %s", indent, *task.FinishedAt), m.width))
								b.WriteString("\n")
							}
							b.WriteString("\n")
						}

						cursorIdx++
					}
				}
			}
		}
	}

	oldY := m.viewport.YPosition
	m.viewport.SetContent(b.String())
	m.viewport.YPosition = oldY
}

func (m RunDetailModel) View() string {
	if m.ready {
		return m.viewport.View()
	}
	var b strings.Builder
	if m.run == nil {
		b.WriteString("\n")
		b.WriteString(lipgloss.NewStyle().Foreground(lipgloss.Color("#666666")).Render("(select a run)"))
		b.WriteString("\n")
	}
	return b.String()
}
