package components

import (
	"strings"

	"github.com/charmbracelet/lipgloss"
	truncate "github.com/muesli/reflow/truncate"
)

var (
	ColorPending   = lipgloss.Color("#FFA500")
	ColorRunning   = lipgloss.Color("#FFFF00")
	ColorSuccess   = lipgloss.Color("#00FF00")
	ColorFailed    = lipgloss.Color("#FF0000")
	ColorSkipped   = lipgloss.Color("#00FFFF")
	ColorCancelled = lipgloss.Color("#FF00FF")
	ColorCyan      = lipgloss.Color("#00FFFF")
	ColorWhite     = lipgloss.Color("#FFFFFF")
	ColorDim       = lipgloss.Color("#666666")
	ColorLabel     = lipgloss.Color("#888888")
	ColorGold      = lipgloss.Color("#FFD700")
	ColorBarBg     = lipgloss.Color("#333333")
	ColorBorder    = lipgloss.Color("#555555")
)

var (
	PanelStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(ColorBorder).
			Padding(0, 1)

	FocusedPanelStyle = PanelStyle.Copy().
				BorderForeground(ColorCyan)

	LeftPanelBorder = lipgloss.Border{
		Top:         "─",
		Bottom:      "─",
		Left:        "│",
		Right:       "",
		TopLeft:     "╭",
		TopRight:    "─",
		BottomLeft:  "╰",
		BottomRight: "─",
	}

	RightPanelBorder = lipgloss.Border{
		Top:         "─",
		Bottom:      "─",
		Left:        "",
		Right:       "│",
		TopLeft:     "─",
		TopRight:    "╮",
		BottomLeft:  "─",
		BottomRight: "╯",
	}

	LeftPanelStyle = lipgloss.NewStyle().
			Border(LeftPanelBorder).
			BorderForeground(ColorBorder).
			Padding(0, 1)

	FocusedLeftPanelStyle = LeftPanelStyle.Copy().
				BorderForeground(ColorCyan)

	RightPanelStyle = lipgloss.NewStyle().
			Border(RightPanelBorder).
			BorderForeground(ColorBorder).
			Padding(0, 1)

	FocusedRightPanelStyle = RightPanelStyle.Copy().
				BorderForeground(ColorCyan)

	DividerStyle = lipgloss.NewStyle().Foreground(ColorBorder)

	TitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorCyan)

	DimStyle   = lipgloss.NewStyle().Foreground(ColorDim)
	LabelStyle = lipgloss.NewStyle().Foreground(ColorLabel)

	CursorStyle = lipgloss.NewStyle().Foreground(ColorCyan).Bold(true)

	SubpipelineStyle = lipgloss.NewStyle().
				Bold(true).
				Foreground(ColorGold)

	StatusPendingStyle   = lipgloss.NewStyle().Foreground(ColorPending)
	StatusRunningStyle   = lipgloss.NewStyle().Foreground(ColorRunning)
	StatusSuccessStyle   = lipgloss.NewStyle().Foreground(ColorSuccess)
	StatusFailedStyle    = lipgloss.NewStyle().Foreground(ColorFailed)
	StatusSkippedStyle   = lipgloss.NewStyle().Foreground(ColorSkipped)
	StatusCancelledStyle = lipgloss.NewStyle().Foreground(ColorCancelled)

	ErrorStyle = lipgloss.NewStyle().
			Foreground(ColorFailed).
			Bold(true)

	ProgressDone = "█"
	ProgressRun  = "▓"
	ProgressTodo = "░"

	TreeBranch = "├─"
	TreeLast   = "└─"
	TreeBar    = "│ "
)

func StatusIcon(status string) string {
	switch status {
	case "running":
		return "▶"
	case "pending":
		return "○"
	case "success":
		return "✔"
	case "failed":
		return "✘"
	case "skipped":
		return "⊘"
	case "cancelled":
		return "✕"
	default:
		return "?"
	}
}

func StatusStyle(status string) lipgloss.Style {
	switch status {
	case "running":
		return StatusRunningStyle
	case "pending":
		return StatusPendingStyle
	case "success":
		return StatusSuccessStyle
	case "failed":
		return StatusFailedStyle
	case "skipped":
		return StatusSkippedStyle
	case "cancelled":
		return StatusCancelledStyle
	default:
		return lipgloss.NewStyle()
	}
}

func TruncateLine(line string, maxWidth int) string {
	if maxWidth <= 0 || lipgloss.Width(line) <= maxWidth {
		return line
	}
	if maxWidth <= 3 {
		return ""
	}
	return truncate.StringWithTail(line, uint(maxWidth), "...")
}

func FormatTime(t *string) string {
	if t == nil {
		return "-"
	}
	s := *t
	if len(s) >= 19 {
		return s[5:19]
	}
	return s
}

func MakeProgressBar(done, running, total, barW int) string {
	if total == 0 || barW <= 0 {
		return ""
	}
	doneW := barW * done / total
	runW := barW * running / total
	todoW := barW - doneW - runW
	if todoW < 0 {
		todoW = 0
	}
	if doneW+runW > barW {
		doneW = barW - runW
		if doneW < 0 {
			doneW = 0
			runW = barW
		}
	}

	bar := StatusSuccessStyle.Render(strings.Repeat(ProgressDone, doneW)) +
		StatusRunningStyle.Render(strings.Repeat(ProgressRun, runW)) +
		DimStyle.Render(strings.Repeat(ProgressTodo, todoW))
	return bar
}
