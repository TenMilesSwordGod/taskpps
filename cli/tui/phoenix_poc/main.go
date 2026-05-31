package main

import (
	"fmt"
	"os"
	"time"

	phoenix "github.com/phoenix-tui/phoenix"
	tea "github.com/phoenix-tui/phoenix/tea/api"
	"github.com/phoenix-tui/phoenix/components/list/api"
	"github.com/phoenix-tui/phoenix/components/progress/api"
	"github.com/phoenix-tui/phoenix/components/viewport/api"
)

type AppState struct {
	runs        []Run
	selectedIdx int
	tab         int
	loading     bool
	lastRefresh time.Time
}

type Run struct {
	ID           string
	Name         string
	Status       string
	Progress     float64
	TaskCount    int
	CompletedCnt int
}

type Model struct {
	state  AppState
	list   list.Model
	detail viewport.Model
	progress progress.Bar
}

func (m Model) Init() tea.Cmd {
	return m.fetchRuns
}

func (m Model) Update(msg tea.Msg) (Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		return m.handleKey(msg)
		
	case tea.WindowSizeMsg:
		m.resize(msg.Width, msg.Height)
		return m, nil
		
	case runsFetchedMsg:
		m.state.runs = msg.runs
		m.state.loading = false
		m.state.lastRefresh = time.Now()
		m.updateList()
		return m, nil
		
	case runSelectedMsg:
		m.state.selectedIdx = msg.idx
		m.updateDetail()
		return m, nil
		
	case tickMsg:
		if time.Since(m.state.lastRefresh) > 2*time.Second {
			return m, m.fetchRuns
		}
		return m, tea.Tick(time.Second, func(_ time.Time) tea.Msg { return tickMsg{} })
	}
	
	return m, nil
}

func (m Model) View() string {
	style := phoenix.NewStyle().
		Background("#1a1a2e").
		Foreground("#e0e0e0").
		Padding(1)

	header := phoenix.NewStyle().
		Bold(true).
		Foreground("#00ff00").
		Render(" ppsctl watch ")

	status := fmt.Sprintf(" Runs:%d Tasks:%d/%d %s ",
		len(m.state.runs),
		m.totalCompleted(),
		m.totalTasks(),
		m.state.lastRefresh.Format("15:04:05"),
	)

	mainContent := m.renderMainContent()

	return style.Render(
		phoenix.JoinVertical(
			phoenix.JoinHorizontal(header, phoenix.Right(status)),
			phoenix.Border(phoenix.Rounded, "#16213e", mainContent),
		),
	)
}

func (m *Model) handleKey(msg tea.KeyMsg) (Model, tea.Cmd) {
	switch msg.String() {
	case "q", "ctrl+c":
		return *m, phoenix.Quit()
	case "up", "k":
		if m.state.selectedIdx > 0 {
			m.state.selectedIdx--
			m.updateDetail()
		}
	case "down", "j":
		if m.state.selectedIdx < len(m.state.runs)-1 {
			m.state.selectedIdx++
			m.updateDetail()
		}
	case "tab":
		m.state.tab = (m.state.tab + 1) % 2
	case "r":
		m.state.loading = true
		return *m, m.fetchRuns
	}
	return *m, nil
}

func (m *Model) fetchRuns() tea.Msg {
	time.Sleep(100 * time.Millisecond)
	return runsFetchedMsg{
		runs: []Run{
			{ID: "run-001", Name: "CI Build & Publish", Status: "success", Progress: 100, TaskCount: 3, CompletedCnt: 3},
			{ID: "run-002", Name: "Deploy to Staging", Status: "running", Progress: 66.7, TaskCount: 3, CompletedCnt: 2},
			{ID: "run-003", Name: "E2E Tests", Status: "pending", Progress: 0, TaskCount: 5, CompletedCnt: 0},
		},
	}
}

func (m *Model) updateList() {
	items := make([]list.Item, len(m.state.runs))
	for i, run := range m.state.runs {
		items[i] = list.Item{
			Value: run,
			Text:  fmt.Sprintf(" %s %s (%.0f%%)", statusIcon(run.Status), run.Name, run.Progress),
		}
	}
	m.list.SetItems(items)
	m.list.Select(m.state.selectedIdx)
}

func (m *Model) updateDetail() {
	if m.state.selectedIdx >= 0 && m.state.selectedIdx < len(m.state.runs) {
		run := m.state.runs[m.state.selectedIdx]
		content := fmt.Sprintf(" Run ID: %s\n\n Status: %s\n Progress: %.1f%%\n Tasks: %d/%d",
			run.ID,
			run.Status,
			run.Progress,
			run.CompletedCnt,
			run.TaskCount,
		)
		m.detail.SetContent(content)
	}
}

func (m *Model) resize(w, h int) {
	m.list.SetSize(w/2-2, h-4)
	m.detail.SetSize(w/2-2, h-4)
}

func (m Model) renderMainContent() string {
	leftPanel := m.list.View()
	rightPanel := m.renderRightPanel()
	
	return phoenix.JoinHorizontal(
		phoenix.Border(phoenix.Rounded, "#0f3460", leftPanel),
		" │ ",
		phoenix.Border(phoenix.Rounded, "#0f3460", rightPanel),
	)
}

func (m Model) renderRightPanel() string {
	if m.state.loading {
		spinner := progress.NewSpinner(progress.SpinnerDots).SetLabel("Loading...")
		return spinner.View()
	}
	
	tabs := []string{"▸ Detail ", " Logs "}
	if m.state.tab == 1 {
		tabs[0], tabs[1] = tabs[1], tabs[0]
	}
	
	tabBar := phoenix.NewStyle().Bold(true).Render(
		fmt.Sprintf("%s·%s", tabs[0], tabs[1]),
	)
	
	content := ""
	if m.state.tab == 0 {
		content = m.detail.View()
	} else {
		content = "(no output)"
	}
	
	return phoenix.JoinVertical(tabBar, content)
}

func (m Model) totalCompleted() int {
	total := 0
	for _, r := range m.state.runs {
		total += r.CompletedCnt
	}
	return total
}

func (m Model) totalTasks() int {
	total := 0
	for _, r := range m.state.runs {
		total += r.TaskCount
	}
	return total
}

func statusIcon(status string) string {
	switch status {
	case "success":
		return "✔"
	case "running":
		return "▶"
	case "failed":
		return "✘"
	default:
		return "○"
	}
}

type runsFetchedMsg struct {
	runs []Run
}

type runSelectedMsg struct {
	idx int
}

type tickMsg struct{}

func main() {
	clientURL := os.Getenv("PPS_API_URL")
	if clientURL == "" {
		clientURL = "http://localhost:8080"
	}

	model := Model{
		state: AppState{
			runs:        []Run{},
			selectedIdx: 0,
			tab:         0,
			loading:     true,
		},
		list:    list.New(),
		detail:  viewport.New(),
		progress: progress.NewBar(100).SetWidth(30),
	}

	p := phoenix.NewProgram(model, phoenix.WithAltScreen[Model]())

	fmt.Printf("🚀 Starting ppsctl watch with Phoenix TUI...\n")
	fmt.Printf("   API URL: %s\n", clientURL)
	fmt.Printf("   Press 'q' to quit\n\n")

	if err := p.Run(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
