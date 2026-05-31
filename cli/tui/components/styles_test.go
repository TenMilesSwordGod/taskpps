package components

import (
	"testing"

	"github.com/charmbracelet/lipgloss"
)

func TestStatusIcon(t *testing.T) {
	tests := []struct {
		status   string
		expected string
	}{
		{"running", "▶"},
		{"pending", "○"},
		{"success", "✔"},
		{"failed", "✘"},
		{"skipped", "⊘"},
		{"cancelled", "✕"},
		{"unknown", "?"},
	}

	for _, tt := range tests {
		t.Run(tt.status, func(t *testing.T) {
			result := StatusIcon(tt.status)
			if result != tt.expected {
				t.Errorf("StatusIcon(%q) = %q, want %q", tt.status, result, tt.expected)
			}
		})
	}
}

func TestStatusStyle(t *testing.T) {
	tests := []string{"running", "pending", "success", "failed", "skipped", "cancelled", "unknown"}
	for _, status := range tests {
		t.Run(status, func(t *testing.T) {
			style := StatusStyle(status)
			result := style.Render("test")
			if result == "" {
				t.Error("expected non-empty style render")
			}
		})
	}
}

func TestStyleDefinitions(t *testing.T) {
	t.Run("PanelStyle", func(t *testing.T) {
		result := PanelStyle.Render("test")
		if result == "" {
			t.Error("PanelStyle rendered empty")
		}
	})

	t.Run("FocusedPanelStyle", func(t *testing.T) {
		result := FocusedPanelStyle.Render("test")
		if result == "" {
			t.Error("FocusedPanelStyle rendered empty")
		}
	})

	t.Run("TitleStyle", func(t *testing.T) {
		result := TitleStyle.Render("test")
		if result == "" {
			t.Error("TitleStyle rendered empty")
		}
	})

	t.Run("HeaderStyle", func(t *testing.T) {
		result := HeaderStyle.Render("test")
		if result == "" {
			t.Error("HeaderStyle rendered empty")
		}
	})

	t.Run("FooterStyle", func(t *testing.T) {
		result := FooterStyle.Render("test")
		if result == "" {
			t.Error("FooterStyle rendered empty")
		}
	})

	t.Run("ErrorStyle", func(t *testing.T) {
		result := ErrorStyle.Render("test")
		if result == "" {
			t.Error("ErrorStyle rendered empty")
		}
	})

	t.Run("CursorStyle", func(t *testing.T) {
		result := CursorStyle.Render("test")
		if result == "" {
			t.Error("CursorStyle rendered empty")
		}
	})
}

func TestColorDefinitions(t *testing.T) {
	colors := []lipgloss.Color{
		ColorPending,
		ColorRunning,
		ColorSuccess,
		ColorFailed,
		ColorSkipped,
		ColorCancelled,
		ColorCyan,
		ColorWhite,
	}
	for i, c := range colors {
		if c == "" {
			t.Errorf("color at index %d is empty", i)
		}
	}
}

func TestWidthStyle(t *testing.T) {
	t.Run("panel_style_width", func(t *testing.T) {
		styled := PanelStyle.Width(50).Render("content")
		if styled == "" {
			t.Error("width style rendered empty")
		}
	})

	t.Run("focused_panel_style_width", func(t *testing.T) {
		styled := FocusedPanelStyle.Width(50).Render("content")
		if styled == "" {
			t.Error("focused width style rendered empty")
		}
	})
}

func TestTruncateLine(t *testing.T) {
	t.Run("no_truncation_needed", func(t *testing.T) {
		result := TruncateLine("hello", 10)
		if result != "hello" {
			t.Errorf("TruncateLine = %q, want %q", result, "hello")
		}
	})

	t.Run("truncation_with_ellipsis", func(t *testing.T) {
		result := TruncateLine("hello world", 8)
		if lipgloss.Width(result) > 8 {
			t.Errorf("TruncateLine width = %d, want <= 8, got %q", lipgloss.Width(result), result)
		}
		if len(result) > 0 && result[len(result)-3:] != "..." {
			t.Errorf("TruncateLine should end with ..., got %q", result)
		}
	})

	t.Run("zero_width", func(t *testing.T) {
		result := TruncateLine("hello", 0)
		if result != "hello" {
			t.Errorf("TruncateLine with width 0 should return original, got %q", result)
		}
	})

	t.Run("very_small_width", func(t *testing.T) {
		result := TruncateLine("hello", 3)
		if lipgloss.Width(result) > 3 {
			t.Errorf("TruncateLine width = %d, want <= 3, got %q", lipgloss.Width(result), result)
		}
	})

	t.Run("unicode_characters", func(t *testing.T) {
		result := TruncateLine("▶ ✔ ✘ ○", 6)
		if lipgloss.Width(result) > 6 {
			t.Errorf("TruncateLine with unicode width = %d, want <= 6, got %q", lipgloss.Width(result), result)
		}
	})

	t.Run("styled_text", func(t *testing.T) {
		styled := StatusRunningStyle.Render("running task with a very long name")
		result := TruncateLine(styled, 15)
		if lipgloss.Width(result) > 15 {
			t.Errorf("TruncateLine with styled text width = %d, want <= 15, got %q", lipgloss.Width(result), result)
		}
	})
}

func TestSubpipelineStyle(t *testing.T) {
	result := SubpipelineStyle.Render("build")
	if result == "" {
		t.Error("SubpipelineStyle rendered empty")
	}
}

func TestTreeConnectors(t *testing.T) {
	if TreeConnector == "" {
		t.Error("TreeConnector should not be empty")
	}
	if TreeBranch == "" {
		t.Error("TreeBranch should not be empty")
	}
	if TreeLast == "" {
		t.Error("TreeLast should not be empty")
	}
}