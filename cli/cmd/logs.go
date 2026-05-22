package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var logFollow bool
var logTask string
var logTail int

var logsCmd = &cobra.Command{
	Use:   "logs <run-id>",
	Short: "View task logs",
	Long: `View logs for a pipeline run, with optional follow mode for real-time output.

Examples:
  ppsctl logs abc123def456
  ppsctl logs abc123def456 --task build
  ppsctl logs abc123def456 -f
  ppsctl logs abc123def456 --tail 100
`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		runID := args[0]

		if logFollow {
			color.Cyan("Following logs for run %s\n", runID)
			return apiClient.FollowLogs(runID, logTask, func(taskName, line string) {
				if taskName != "" {
					fmt.Printf("[%s] %s\n", taskName, line)
				} else {
					fmt.Print(line)
				}
			})
		}

		logs, err := apiClient.GetLogs(runID, logTask, logTail)
		if err != nil {
			return err
		}

		if len(logs) == 0 {
			fmt.Println("No logs available.")
			return nil
		}

		for taskName, content := range logs {
			taskColor := color.New(color.FgCyan)
			taskColor.Printf("=== %s ===\n", taskName)
			fmt.Print(content)
			if len(content) > 0 && content[len(content)-1] != '\n' {
				fmt.Println()
			}
		}
		return nil
	},
}

func init() {
	logsCmd.Flags().BoolVarP(&logFollow, "follow", "f", false, "follow log output in real-time")
	logsCmd.Flags().StringVar(&logTask, "task", "", "show logs for a specific task")
	logsCmd.Flags().IntVar(&logTail, "tail", 0, "show only last N lines")
	RootCmd.AddCommand(logsCmd)
}
