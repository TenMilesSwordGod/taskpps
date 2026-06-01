package tui

import (
	"strings"
	"testing"

	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/models"
)

func TestViewNotReady(t *testing.T) {
	m := makeTestModel()
	view := m.View()
	if !strings.Contains(view, "Initializing") {
		t.Errorf("view should show Initializing, got: %s", view)
	}
}

func TestViewQuitting(t *testing.T) {
	m := makeTestModel()
	m.state.Quit = true
	view := m.View()
	if view != "" {
		t.Errorf("view should be empty when quitting, got: %s", view)
	}
}

func TestViewReady(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	view := m.View()
	if view == "" {
		t.Error("view should not be empty when ready")
	}
	if !strings.Contains(view, "ppsctl watch") {
		t.Errorf("view should contain header, got: %s", view)
	}
}

func TestViewWithError(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.ErrorMsg = "Connection refused"

	view := m.View()
	if !strings.Contains(view, "ERR:") {
		t.Errorf("view should contain ERR, got: %s", view)
	}
}

func TestViewWithRuns(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 150
	m.state.Height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "def67890", PipelineName: "build", Status: models.RunStatusSuccess},
	}
	m.state.Runs = runs
	m.runList.SetRuns(runs)

	view := m.View()
	if view == "" {
		t.Error("view should not be empty")
	}
}

func TestViewPanelFocus(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 150
	m.state.Height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
	}
	m.state.Runs = runs
	m.runList.SetRuns(runs)

	t.Run("focus_runlist", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RunList focus")
		}
	})

	t.Run("focus_rundetail", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RightPanel focus")
		}
	})

	t.Run("focus_logviewer", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RightPanel focus")
		}
	})
}

func TestViewNarrowTerminal(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 80
	m.state.Height = 30
	m.resizeComponents()

	view := m.View()
	if view == "" {
		t.Error("view should render on narrow terminal")
	}
}

func TestViewWideTerminal(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 200
	m.state.Height = 50
	m.resizeComponents()

	view := m.View()
	if view == "" {
		t.Error("view should render on wide terminal")
	}
}

func TestViewEmptyRuns(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = nil
	m.runList.SetRuns(nil)

	view := m.View()
	if view == "" {
		t.Error("view should render with empty runs")
	}
}

func TestViewRenderFooter(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	m := NewModel(c, "")
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = []models.Run{{ID: "1", PipelineName: "test", Status: models.RunStatusRunning}}
	m.runList.SetRuns(m.state.Runs)

	footer := renderFooter(120, m.state, &m)
	if !strings.Contains(footer, "Runs:") {
		t.Errorf("footer should show Runs count, got: %s", footer)
	}
	if !strings.Contains(footer, "Tasks:") {
		t.Errorf("footer should show Tasks count, got: %s", footer)
	}
	if !strings.Contains(footer, "quit") {
		t.Errorf("footer should show key hints, got: %s", footer)
	}
}

func TestViewHeader(t *testing.T) {
	header := renderHeader(120)
	if !strings.Contains(header, "ppsctl watch") {
		t.Errorf("header should contain title, got: %s", header)
	}
	if !strings.Contains(header, "pipeline task monitor") {
		t.Errorf("header should contain subtitle, got: %s", header)
	}
}

func TestViewHeaderNarrow(t *testing.T) {
	header := renderHeader(40)
	if header == "" {
		t.Error("header should render on narrow width")
	}
}