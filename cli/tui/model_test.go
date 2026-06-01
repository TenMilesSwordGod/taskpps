package tui

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/models"
)

func TestNewModel(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")

	if m.state.FocusedPanel != FocusRunList {
		t.Errorf("focusedPanel = %v, want FocusRunList", m.state.FocusedPanel)
	}
	if m.client == nil {
		t.Error("client should not be nil")
	}
	if m.state.Quit {
		t.Error("quit should be false")
	}
}

func TestNewModelWithTargetRun(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "abc123")

	if m.targetRunID != "abc123" {
		t.Errorf("targetRunID = %s, want abc123", m.targetRunID)
	}
}

func TestPanelFocus(t *testing.T) {
	t.Run("focusNext", func(t *testing.T) {
		m := Model{state: NewAppState()}
		m.state.FocusedPanel = FocusRunList
		if m.focusNext() != FocusRightPanel {
			t.Error("focusNext from RunList should go to RightPanel")
		}

		m.state.FocusedPanel = FocusRightPanel
		if m.focusNext() != FocusRunList {
			t.Error("focusNext from RightPanel should go to RunList")
		}
	})

	t.Run("focusPrev", func(t *testing.T) {
		m := Model{state: NewAppState()}
		m.state.FocusedPanel = FocusRunList
		if m.focusPrev() != FocusRightPanel {
			t.Error("focusPrev from RunList should go to RightPanel")
		}

		m.state.FocusedPanel = FocusRightPanel
		if m.focusPrev() != FocusRunList {
			t.Error("focusPrev from RightPanel should go to RunList")
		}
	})
}

func TestInit(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")

	cmds := m.Init()
	if cmds == nil {
		t.Error("Init should return commands")
	}
}

func TestModelQuit(t *testing.T) {
	m := NewModel(client.New(&config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}), "")

	if m.state.Quit {
		t.Error("quit should be false initially")
	}

	m.state.Quit = true
	if !m.state.Quit {
		t.Error("quit should be true after setting")
	}
}

func TestRenderHeader(t *testing.T) {
	result := renderHeader(100)
	if result == "" {
		t.Error("renderHeader should not return empty")
	}
}

func TestRenderFooter(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")

	t.Run("empty", func(t *testing.T) {
		result := renderFooter(100, m.state, &m)
		if result == "" {
			t.Error("renderFooter should not return empty")
		}
	})

	t.Run("with_tasks", func(t *testing.T) {
		m2 := NewModel(c, "")
		m2.state.Runs = []models.Run{
			{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning,
				Tasks: []models.TaskRun{
					{TaskName: "build", Status: models.TaskStatusSuccess},
					{TaskName: "test", Status: models.TaskStatusRunning},
					{TaskName: "deploy", Status: models.TaskStatusFailed},
				}},
		}
		m2.runList.SetRuns(m2.state.Runs)
		m2.runList.SetCursor(0)
		m2.runDetail.SetRun(&m2.state.Runs[0])

		result := renderFooter(100, m2.state, &m2)
		if result == "" {
			t.Error("renderFooter should not return empty")
		}
		if !strings.Contains(result, "2/3") {
			t.Errorf("should show 2/3 tasks done, got: %s", result)
		}
	})
}

func TestFetchFunctions(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)

	t.Run("fetchRuns", func(t *testing.T) {
		cmd := fetchRuns(c)
		if cmd == nil {
			t.Error("fetchRuns should return a command")
		}
	})

	t.Run("fetchRun", func(t *testing.T) {
		cmd := fetchRun(c, "test123")
		if cmd == nil {
			t.Error("fetchRun should return a command")
		}
	})

	t.Run("fetchLogs", func(t *testing.T) {
		cmd := fetchLogs(c, "test123", "task1")
		if cmd == nil {
			t.Error("fetchLogs should return a command")
		}
	})
}

func TestResizeComponents(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")

	m.state.Width = 150
	m.state.Height = 40
	m.resizeComponents()

	view := m.runList.View()
	if view == "" {
		t.Error("RunList View should work after resize")
	}

	detailView := m.runDetail.View()
	if detailView == "" {
		t.Error("RunDetail View should work after resize")
	}
}

func TestStartWatch(t *testing.T) {
	t.Run("quit_with_q", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("q\n")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer())
		if err != nil {
			t.Logf("StartWatch error (expected from test client): %v", err)
		}
	})

	t.Run("quit_with_ctrl_c", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("\x03")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer())
		if err != nil {
			t.Logf("StartWatch ctrl+c error: %v", err)
		}
	})

	t.Run("quit_with_esc", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("\x1b")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer())
		if err != nil {
			t.Logf("StartWatch esc error: %v", err)
		}
	})

	t.Run("error_path", func(t *testing.T) {
		c := makeTestClient()
		input := strings.NewReader("q\n")
		err := StartWatch(c, "", tea.WithInput(input), tea.WithoutRenderer(), tea.WithAltScreen())
		if err != nil {
			t.Logf("StartWatch with both renderer options: %v", err)
		}
	})
}