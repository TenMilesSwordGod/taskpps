package cmd

import (
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/tui"
)

var watchCmd = &cobra.Command{
	Use:   "watch [run-id]",
	Short: "Interactive TUI to monitor pipeline runs",
	Long: `Launch an interactive Terminal User Interface (TUI) to monitor
pipeline runs in real-time.

Features:
  - Browse run history with ↑/↓ keys
  - Expand tasks to view logs with Enter
  - Scroll logs with PgUp/PgDown
  - Switch panels with Tab / ←→
  - Press r to refresh, q to quit

Examples:
  ppsctl watch              # Browse all runs
  ppsctl watch abc123       # Watch specific run
`,
	Args: cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		runID := ""
		if len(args) > 0 {
			runID = args[0]
		}
		return tui.StartWatch(apiClient, runID)
	},
}

func init() {
	RootCmd.AddCommand(watchCmd)
}