package components

import "github.com/charmbracelet/lipgloss"

var (
	ColorPending   = lipgloss.Color("#FFA500")
	ColorRunning   = lipgloss.Color("#FFFF00")
	ColorSuccess   = lipgloss.Color("#00FF00")
	ColorFailed    = lipgloss.Color("#FF0000")
	ColorSkipped   = lipgloss.Color("#00FFFF")
	ColorCancelled = lipgloss.Color("#FF00FF")
	ColorCyan      = lipgloss.Color("#00FFFF")
	ColorWhite     = lipgloss.Color("#FFFFFF")
)

var (
	PanelStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			Padding(1, 1)

	FocusedPanelStyle = PanelStyle.Copy().
				BorderForeground(ColorCyan)

	TitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(ColorCyan)

	HeaderStyle = lipgloss.NewStyle().
			Background(lipgloss.Color("#333333")).
			Foreground(ColorWhite).
			Padding(0, 1)

	FooterStyle = lipgloss.NewStyle().
			Background(lipgloss.Color("#333333")).
			Foreground(ColorWhite).
			Padding(0, 1)

	ErrorStyle = lipgloss.NewStyle().
			Foreground(ColorFailed).
			Bold(true)

	StatusPendingStyle   = lipgloss.NewStyle().Foreground(ColorPending)
	StatusRunningStyle   = lipgloss.NewStyle().Foreground(ColorRunning)
	StatusSuccessStyle   = lipgloss.NewStyle().Foreground(ColorSuccess)
	StatusFailedStyle    = lipgloss.NewStyle().Foreground(ColorFailed)
	StatusSkippedStyle   = lipgloss.NewStyle().Foreground(ColorSkipped)
	StatusCancelledStyle = lipgloss.NewStyle().Foreground(ColorCancelled)

	CursorStyle = lipgloss.NewStyle().Foreground(ColorCyan).Bold(true)
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