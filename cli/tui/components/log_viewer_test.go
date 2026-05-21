package components

import (
	"fmt"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
)

func TestNewLogViewerModel(t *testing.T) {
	m := NewLogViewerModel()
	if m.ready {
		t.Error("model should not be ready initially")
	}
	if m.Content() != "" {
		t.Error("content should be empty initially")
	}
}

func TestLogViewerSetContent(t *testing.T) {
	t.Run("empty", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetContent("")
		if m.Content() != "" {
			t.Error("content should be empty")
		}
	})

	t.Run("single_line", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetContent("hello world")
		if m.Content() != "hello world" {
			t.Errorf("content = %q, want %q", m.Content(), "hello world")
		}
	})

	t.Run("multi_line", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetContent("line1\nline2\nline3")
		if !strings.Contains(m.Content(), "line1") {
			t.Error("content should contain line1")
		}
	})

	t.Run("overwrite", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetContent("old")
		m.SetContent("new")
		if m.Content() != "new" {
			t.Errorf("content = %q, want %q", m.Content(), "new")
		}
	})
}

func TestLogViewerAppendContent(t *testing.T) {
	m := NewLogViewerModel()
	m.AppendContent("hello ")
	m.AppendContent("world")
	if m.Content() != "hello world" {
		t.Errorf("content = %q, want %q", m.Content(), "hello world")
	}
}

func TestLogViewerSetSize(t *testing.T) {
	m := NewLogViewerModel()
	m.SetSize(80, 24)
	if !m.ready {
		t.Error("model should be ready after SetSize")
	}
}

func TestLogViewerUpdate(t *testing.T) {
	m := NewLogViewerModel()
	m.SetContent("line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8\nline9\nline10")
	m.SetSize(80, 10)

	t.Run("pgdown_scrolls", func(t *testing.T) {
		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyPgDown})
		view := m2.View()
		if view == "" {
			t.Error("view should not be empty")
		}
	})

	t.Run("pgup_scrolls", func(t *testing.T) {
		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyPgUp})
		view := m2.View()
		if view == "" {
			t.Error("view should not be empty")
		}
	})

	t.Run("home_scrolls_to_top", func(t *testing.T) {
		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyHome})
		view := m2.View()
		if view == "" {
			t.Error("view should not be empty")
		}
	})

	t.Run("end_scrolls_to_bottom", func(t *testing.T) {
		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyEnd})
		view := m2.View()
		if view == "" {
			t.Error("view should not be empty")
		}
	})

	t.Run("non_keyboard_msg", func(t *testing.T) {
		m2, _ := m.Update(tea.WindowSizeMsg{Width: 100, Height: 30})
		if m2.Content() != m.Content() {
			t.Error("content should be preserved on WindowSizeMsg")
		}
	})

	t.Run("other_key_msg", func(t *testing.T) {
		m2, _ := m.Update(tea.KeyMsg{Type: tea.KeySpace})
		view := m2.View()
		if view == "" {
			t.Error("view should handle other keys")
		}
	})
}

func TestLogViewerView(t *testing.T) {
	t.Run("empty", func(t *testing.T) {
		m := NewLogViewerModel()
		view := m.View()
		if !strings.Contains(view, "(no output)") {
			t.Errorf("view should show empty message, got: %s", view)
		}
	})

	t.Run("with_content_ready", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetContent("test log")
		m.SetSize(80, 10)
		view := m.View()
		if !strings.Contains(view, "test log") {
			t.Errorf("view should contain content, got: %s", view)
		}
	})

	t.Run("with_content_not_ready", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetContent("test log")
		view := m.View()
		if !strings.Contains(view, "test log") {
			t.Errorf("view should contain fallback content, got: %s", view)
		}
	})

	t.Run("long_content_not_ready", func(t *testing.T) {
		m := NewLogViewerModel()
		long := ""
		for i := 0; i < 30; i++ {
			long += "line " + fmt.Sprintf("%d", i) + "\n"
		}
		m.SetContent(long)
		view := m.View()
		if !strings.Contains(view, "line 29") {
			t.Errorf("view should contain last lines, got: %s", view)
		}
	})

	t.Run("content_ready_with_scroll_hint", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetSize(80, 20)
		m.SetContent("log content")
		view := m.View()
		if !strings.Contains(view, "scroll with PgUp/PgDown") {
			t.Errorf("view should show scroll hint when ready, got: %s", view)
		}
	})
}

func TestLogViewerReadyBranch(t *testing.T) {
	t.Run("SetSize_twice_uses_resize_branch", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetSize(80, 20)
		m.SetSize(60, 15)
		if !m.ready {
			t.Error("should still be ready after second SetSize")
		}
	})

	t.Run("SetContent_when_ready", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetSize(80, 20)
		m.SetContent("hello world")
		if !m.ready {
			t.Error("should be ready")
		}
	})

	t.Run("AppendContent_when_ready", func(t *testing.T) {
		m := NewLogViewerModel()
		m.SetSize(80, 20)
		m.AppendContent("hello")
		m.AppendContent(" world")
		if m.Content() != "hello world" {
			t.Errorf("content = %q", m.Content())
		}
	})
}