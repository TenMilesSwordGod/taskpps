package components

import (
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/models"
)

func TestNewRunListModel(t *testing.T) {
	m := NewRunListModel()
	if m.cursor != 0 {
		t.Errorf("cursor = %d, want 0", m.cursor)
	}
}

func TestRunListSetRuns(t *testing.T) {
	m := NewRunListModel()
	runs := []models.Run{
		{ID: "run1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "run2", PipelineName: "build", Status: models.RunStatusSuccess},
		{ID: "run3", PipelineName: "test", Status: models.RunStatusFailed},
	}
	m.SetRuns(runs)

	if len(m.runs) != 3 {
		t.Errorf("runs length = %d, want 3", len(m.runs))
	}
	if m.cursor != 0 {
		t.Errorf("cursor = %d, want 0", m.cursor)
	}
}

func TestRunListSetRunsEmpty(t *testing.T) {
	m := NewRunListModel()
	m.SetRuns(nil)
	if len(m.runs) != 0 {
		t.Error("expected empty runs")
	}
}

func TestRunListSetRunsCursorAdjust(t *testing.T) {
	m := NewRunListModel()
	m.cursor = 5
	runs := []models.Run{{ID: "r1"}, {ID: "r2"}}
	m.SetRuns(runs)

	if m.cursor != 1 {
		t.Errorf("cursor = %d, want 1 (adjusted)", m.cursor)
	}
}

func TestRunListSetSize(t *testing.T) {
	m := NewRunListModel()
	m.SetSize(50, 20)
	if m.width != 50 || m.height != 20 {
		t.Errorf("size = (%d,%d), want (50,20)", m.width, m.height)
	}
}

func TestRunListSetCursor(t *testing.T) {
	m := NewRunListModel()
	m.runs = []models.Run{{ID: "1"}, {ID: "2"}, {ID: "3"}}

	m.SetCursor(1)
	if m.cursor != 1 {
		t.Errorf("cursor = %d, want 1", m.cursor)
	}

	m.SetCursor(-1)
	if m.cursor != 1 {
		t.Error("cursor should not change for invalid index")
	}

	m.SetCursor(10)
	if m.cursor != 1 {
		t.Error("cursor should not change for out of bounds")
	}
}

func TestRunListSelectedRun(t *testing.T) {
	t.Run("empty_list", func(t *testing.T) {
		m := NewRunListModel()
		if m.SelectedRun() != nil {
			t.Error("expected nil for empty list")
		}
	})

	t.Run("with_runs", func(t *testing.T) {
		m := NewRunListModel()
		runs := []models.Run{
			{ID: "abc", PipelineName: "deploy"},
			{ID: "def", PipelineName: "build"},
		}
		m.SetRuns(runs)
		m.SetCursor(0)
		sel := m.SelectedRun()
		if sel == nil || sel.ID != "abc" {
			t.Errorf("selected run = %v, want abc", sel)
		}
	})
}

func TestRunListUpdateNavigation(t *testing.T) {
	m := NewRunListModel()
	m.runs = []models.Run{{ID: "1"}, {ID: "2"}, {ID: "3"}}

	t.Run("down", func(t *testing.T) {
		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{}})
		m3, _ := m2.Update(tea.KeyMsg{Type: tea.KeyDown})
		if m3.cursor != 1 {
			t.Errorf("cursor = %d, want 1 after down", m3.cursor)
		}
	})

	t.Run("down_at_bottom", func(t *testing.T) {
		m2 := m
		m2.cursor = 2
		m3, _ := m2.Update(tea.KeyMsg{Type: tea.KeyDown})
		if m3.cursor != 2 {
			t.Errorf("cursor = %d, want 2 (stay at bottom)", m3.cursor)
		}
	})

	t.Run("up", func(t *testing.T) {
		m2 := m
		m2.cursor = 1
		m3, _ := m2.Update(tea.KeyMsg{Type: tea.KeyUp})
		if m3.cursor != 0 {
			t.Errorf("cursor = %d, want 0 after up", m3.cursor)
		}
	})

	t.Run("up_at_top", func(t *testing.T) {
		m3, _ := m.Update(tea.KeyMsg{Type: tea.KeyUp})
		if m3.cursor != 0 {
			t.Errorf("cursor = %d, want 0 (stay at top)", m3.cursor)
		}
	})
}

func TestRunListView(t *testing.T) {
	t.Run("empty", func(t *testing.T) {
		m := NewRunListModel()
		view := m.View()
		if !strings.Contains(view, "(no runs)") {
			t.Errorf("view should show empty message, got: %s", view)
		}
	})

	t.Run("with_runs", func(t *testing.T) {
		m := NewRunListModel()
		runs := []models.Run{
			{ID: "abc12345", PipelineName: "deploy", Status: models.RunStatusRunning},
			{ID: "def67890", PipelineName: "build", Status: models.RunStatusSuccess},
		}
		m.SetRuns(runs)
		m.SetSize(60, 10)
		view := m.View()
		if !strings.Contains(view, "abc12345") {
			t.Errorf("view should contain run ID, got: %s", view)
		}
		if !strings.Contains(view, "deploy") {
			t.Errorf("view should contain pipeline name, got: %s", view)
		}
	})

	t.Run("all_statuses", func(t *testing.T) {
		m := NewRunListModel()
		runs := []models.Run{
			{ID: "r1abcdefg", PipelineName: "p1", Status: models.RunStatusPending},
			{ID: "r2abcdefg", PipelineName: "p2", Status: models.RunStatusRunning},
			{ID: "r3abcdefg", PipelineName: "p3", Status: models.RunStatusSuccess},
			{ID: "r4abcdefg", PipelineName: "p4", Status: models.RunStatusFailed},
			{ID: "r5abcdefg", PipelineName: "p5", Status: models.RunStatusCancelled},
		}
		m.SetRuns(runs)
		m.SetSize(60, 20)
		view := m.View()
		for _, r := range runs {
			if !strings.Contains(view, r.ID[:8]) {
				t.Errorf("view should contain ID prefix for %q", r.ID)
			}
		}
	})

	t.Run("small_height", func(t *testing.T) {
		m := NewRunListModel()
		runs := []models.Run{
			{ID: "r1abcdefg", PipelineName: "p1", Status: models.RunStatusRunning},
			{ID: "r2abcdefg", PipelineName: "p2", Status: models.RunStatusSuccess},
		}
		m.SetRuns(runs)
		m.SetSize(60, 5)
		view := m.View()
		if view == "" {
			t.Error("view should not be empty with small height")
		}
	})

	t.Run("width_truncation", func(t *testing.T) {
		m := NewRunListModel()
		runs := []models.Run{
			{ID: "verylongrunid", PipelineName: "verylongpipelinename", Status: models.RunStatusRunning},
		}
		m.SetRuns(runs)
		m.SetSize(20, 10)
		view := m.View()
		if view == "" {
			t.Error("view should handle width truncation")
		}
	})
}