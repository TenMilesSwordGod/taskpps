package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var cancelCmd = &cobra.Command{
	Use:   "cancel <run-id>",
	Short: "Cancel a running pipeline",
	Long: `Cancel a pipeline run. Running tasks will be interrupted and pending
tasks will be marked as cancelled.

Example:
  ppsctl cancel abc123def456
`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		runID := args[0]

		color.Yellow("Cancelling run %s...\n", runID)

		if err := apiClient.CancelRun(runID); err != nil {
			return err
		}

		color.Green("Run %s cancelled successfully.\n", runID)
		return nil
	},
}

func init() {
	RootCmd.AddCommand(cancelCmd)
}
