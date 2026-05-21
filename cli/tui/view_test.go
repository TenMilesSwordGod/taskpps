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
	m.quit = true
	view := m.View()
	if view != "" {
		t.Errorf("view should be empty when quitting, got: %s", view)
	}
}

func TestViewReady(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
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
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()
	m.errMsg = "Connection refused"

	view := m.View()
	if !strings.Contains(view, "ERROR") {
		t.Errorf("view should contain ERROR, got: %s", view)
	}
	if !strings.Contains(view, "Connection refused") {
		t.Errorf("view should contain error message, got: %s", view)
	}
}

func TestViewWithRuns(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 150
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "def67890", PipelineName: "build", Status: models.RunStatusSuccess},
	}
	m.runs = runs
	m.runList.SetRuns(runs)

	view := m.View()
	if view == "" {
		t.Error("view should not be empty")
	}
}

func TestViewPanelFocus(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 150
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{
		{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
	}
	m.runs = runs
	m.runList.SetRuns(runs)

	t.Run("focus_runlist", func(t *testing.T) {
		m.focusedPanel = FocusRunList
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RunList focus")
		}
	})

	t.Run("focus_rundetail", func(t *testing.T) {
		m.focusedPanel = FocusRunDetail
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with RunDetail focus")
		}
	})

	t.Run("focus_logviewer", func(t *testing.T) {
		m.focusedPanel = FocusLogViewer
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with LogViewer focus")
		}
	})
}

func TestViewNarrowTerminal(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 80
	m.height = 30
	m.resizeComponents()

	view := m.View()
	if view == "" {
		t.Error("view should render on narrow terminal")
	}
}

func TestViewWideTerminal(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 200
	m.height = 50
	m.resizeComponents()

	view := m.View()
	if view == "" {
		t.Error("view should render on wide terminal")
	}
}

func TestViewEmptyRuns(t *testing.T) {
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()
	m.runs = nil
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
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()
	m.runs = []models.Run{{ID: "1", PipelineName: "test", Status: models.RunStatusRunning}}
	m.runList.SetRuns(m.runs)

	footer := renderFooter(120, m)
	if !strings.Contains(footer, "Runs:") {
		t.Errorf("footer should show Runs count, got: %s", footer)
	}
	if !strings.Contains(footer, "Polling every 2s") {
		t.Errorf("footer should show polling info, got: %s", footer)
	}
}

func TestViewHeader(t *testing.T) {
	header := renderHeader(120)
	if !strings.Contains(header, "ppsctl watch") {
		t.Errorf("header should contain title, got: %s", header)
	}
	if !strings.Contains(header, "[q]uit") {
		t.Errorf("header should contain key hints, got: %s", header)
	}
	if !strings.Contains(header, "tab") {
		t.Errorf("header should contain tab hint, got: %s", header)
	}
}

func TestViewHeaderNarrow(t *testing.T) {
	header := renderHeader(40)
	if header == "" {
		t.Error("header should render on narrow width")
	}
}