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
	run         *models.Run
	cursor      int
	expanded    map[int]bool
	subExpanded map[string]bool
	width       int
	height      int
	viewport    viewport.Model
	ready       bool
	groups      []subpipelineGroup
	flatItems   []flatItem
}

type flatItem struct {
	kind    string
	subName string
	taskIdx int
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
}

func (m *RunDetailModel) SetRun(run *models.Run) {
	if run != nil {
		cp := *run
		m.run = &cp
	} else {
		m.run = nil
	}
	m.buildGroups()
	if run != nil {
		for _, g := range m.groups {
			if _, ok := m.subExpanded[g.name]; !ok {
				m.subExpanded[g.name] = true
			}
		}
		m.rebuildFlatItems()
		if m.cursor >= len(m.flatItems) && len(m.flatItems) > 0 {
			m.cursor = len(m.flatItems) - 1
		}
	}
	if m.ready {
		m.updateContent()
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
	m.updateContent()
}

func (m *RunDetailModel) SelectedRun() *models.Run {
	return m.run
}

func (m *RunDetailModel) SetCursor(idx int) {
	if idx >= 0 && idx < len(m.flatItems) {
		m.cursor = idx
	}
}

func (m *RunDetailModel) CollapseAll() {
	m.expanded = make(map[int]bool)
	if m.ready {
		m.updateContent()
	}
}

func (m *RunDetailModel) ExpandAll() {
	if m.run == nil {
		return
	}
	for i := range m.run.Tasks {
		m.expanded[i] = true
	}
	if m.ready {
		m.updateContent()
	}
}

func (m *RunDetailModel) HasExpanded() bool {
	for _, v := range m.expanded {
		if v {
			return true
		}
	}
	return false
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
				m.updateContent()
			} else {
				m.viewport, cmd = m.viewport.Update(msg)
			}
		case "down", "j":
			if m.cursor < len(m.flatItems)-1 {
				m.cursor++
				m.skipCollapsedTasks()
				m.updateContent()
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
				m.updateContent()
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
		if m.subExpanded[item.subName] {
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

func (m *RunDetailModel) updateContent() {
	var b strings.Builder

	if m.run == nil {
		b.WriteString(DimStyle.Render("  (select a run)"))
		b.WriteString("\n")
	} else {
		icon := StatusIcon(string(m.run.Status))
		style := StatusStyle(string(m.run.Status))

		b.WriteString(TruncateLine(fmt.Sprintf("  %s %s  %s", icon, style.Bold(true).Render(string(m.run.Status)), m.run.PipelineName), m.width))
		b.WriteString("\n")

		idStr := m.run.ID
		if len([]rune(idStr)) > 12 {
			idStr = string([]rune(idStr)[:12])
		}
		meta := fmt.Sprintf("  %s%s  %s%s",
			LabelStyle.Render("id:"), DimStyle.Render(idStr),
			LabelStyle.Render("time:"), DimStyle.Render(FormatTime(m.run.StartedAt)))
		b.WriteString(TruncateLine(meta, m.width))
		b.WriteString("\n")

		if m.run.FinishedAt != nil {
			dur := fmt.Sprintf("  %s%s → %s",
				LabelStyle.Render("ran: "),
				DimStyle.Render(FormatTime(m.run.StartedAt)),
				DimStyle.Render(FormatTime(m.run.FinishedAt)))
			b.WriteString(TruncateLine(dur, m.width))
			b.WriteString("\n")
		}

		b.WriteString(TruncateLine(LabelStyle.Render(strings.Repeat("─", min(m.width, 50))), m.width))
		b.WriteString("\n")

		if len(m.run.Tasks) == 0 {
			b.WriteString(DimStyle.Render("  (no tasks)"))
			b.WriteString("\n")
		} else {
			cursorIdx := 0
			for gi, g := range m.groups {
				if gi > 0 {
					b.WriteString(TruncateLine(DimStyle.Render("  "+strings.Repeat("┄", min(m.width-2, 40))), m.width))
					b.WriteString("\n")
				}

				isExpanded := m.subExpanded[g.name]
				expandIcon := "▶"
				if isExpanded {
					expandIcon = "▼"
				}
				groupStatus := subStatus(m.run, g)
				expandIcon = StatusStyle(groupStatus).Render(expandIcon)

				isCursor := cursorIdx < len(m.flatItems) && m.cursor == cursorIdx
				prefix := "  "
				if isCursor {
					prefix = CursorStyle.Render("> ")
				}

				done, running, total := subStats(m.run, g)
			barW := m.width / 4
			if barW < 5 {
				barW = 5
			}
			if barW > 30 {
				barW = 30
			}
			bar := MakeProgressBar(done, running, total, barW)
				prog := ""
				if total > 0 {
					prog = fmt.Sprintf(" %s %d/%d", bar, done, total)
				}

				subLine := fmt.Sprintf("%s%s %s%s",
					prefix, expandIcon,
					SubpipelineStyle.Render(g.name),
					prog)
				b.WriteString(TruncateLine(subLine, m.width))
				b.WriteString("\n")
				cursorIdx++

				if isExpanded {
					for ti, taskIdx := range g.tasks {
						task := m.run.Tasks[taskIdx]
						taskIcon := StatusIcon(string(task.Status))
						taskStyle := StatusStyle(string(task.Status))

						connector := TreeBranch
						if ti == len(g.tasks)-1 {
							connector = TreeLast
						}

						isTaskCursor := cursorIdx < len(m.flatItems) && m.cursor == cursorIdx
						taskPrefix := "  " + connector + " "
						if isTaskCursor {
							taskPrefix = "  " + connector + CursorStyle.Render(" ")
						}

						displayName := task.TaskName
						if idx := strings.Index(displayName, "."); idx >= 0 {
							displayName = displayName[idx+1:]
						}

						line := fmt.Sprintf("%s%s %s %s", taskPrefix, taskIcon, displayName, taskStyle.Render(string(task.Status)))
						if task.ExitCode != nil {
							line += DimStyle.Render(fmt.Sprintf(" exit:%d", *task.ExitCode))
						}
						b.WriteString(TruncateLine(line, m.width))
						b.WriteString("\n")

						if m.expanded[taskIdx] {
							indent := "      "
							if ti < len(g.tasks)-1 {
								indent = "  " + TreeBar + " "
							}

							b.WriteString(TruncateLine(fmt.Sprintf("%s%s %s  %s %s",
								indent,
								LabelStyle.Render("type:"),
								DimStyle.Render(task.TaskType),
								LabelStyle.Render("start:"),
								DimStyle.Render(FormatTime(task.StartedAt))), m.width))
							b.WriteString("\n")

							if task.FinishedAt != nil {
								b.WriteString(TruncateLine(fmt.Sprintf("%s%s %s",
									indent,
									LabelStyle.Render("end:  "),
									DimStyle.Render(FormatTime(task.FinishedAt))), m.width))
								b.WriteString("\n")
							}
						}

						cursorIdx++
					}
				}
			}
		}
	}

	m.viewport.SetContent(b.String())
	m.ensureCursorVisible()
}

func (m *RunDetailModel) ensureCursorVisible() {
	if !m.ready || len(m.flatItems) == 0 {
		return
	}
	cursorLine := m.cursorLineForIndex(m.cursor)
	viewTop := m.viewport.YOffset
	viewBottom := viewTop + m.viewport.Height - 1

	if cursorLine < viewTop {
		m.viewport.SetYOffset(cursorLine)
	} else if cursorLine > viewBottom {
		m.viewport.SetYOffset(cursorLine - m.viewport.Height + 1)
	}
}

func (m *RunDetailModel) cursorLineForIndex(idx int) int {
	if m.run == nil || len(m.flatItems) == 0 || idx >= len(m.flatItems) {
		return 0
	}
	line := 0
	flatIdx := 0
	for _, g := range m.groups {
		if flatIdx == idx {
			return line
		}
		line++
		flatIdx++

		if m.subExpanded[g.name] {
			for ti, taskIdx := range g.tasks {
				if flatIdx == idx {
					return line
				}
				line++
				flatIdx++

				if m.expanded[taskIdx] {
					line++
					if m.run.Tasks[taskIdx].FinishedAt != nil {
						line++
					}
				}
				_ = ti
			}
		}
	}
	return line
}

func subStats(run *models.Run, g subpipelineGroup) (done, running, total int) {
	total = len(g.tasks)
	for _, idx := range g.tasks {
		if idx < len(run.Tasks) {
			s := run.Tasks[idx].Status
			if s == "success" || s == "failed" || s == "skipped" || s == "cancelled" {
				done++
			} else if s == "running" {
				running++
			}
		}
	}
	return
}

func subStatus(run *models.Run, g subpipelineGroup) string {
	hasFailed := false
	hasRunning := false
	hasPending := false
	hasSuccess := false
	hasSkipped := false
	hasCancelled := false
	for _, idx := range g.tasks {
		if idx >= len(run.Tasks) {
			continue
		}
		s := string(run.Tasks[idx].Status)
		switch s {
		case "failed":
			hasFailed = true
		case "running":
			hasRunning = true
		case "pending":
			hasPending = true
		case "success":
			hasSuccess = true
		case "skipped":
			hasSkipped = true
		case "cancelled":
			hasCancelled = true
		}
	}
	if hasFailed {
		return "failed"
	}
	if hasRunning {
		return "running"
	}
	if hasPending {
		return "pending"
	}
	if hasSuccess {
		return "success"
	}
	if hasCancelled {
		return "cancelled"
	}
	if hasSkipped {
		return "skipped"
	}
	return "pending"
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func (m RunDetailModel) View() string {
	if m.ready {
		return m.viewport.View()
	}
	return DimStyle.Render("  (select a run)")
}
