package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
)

var cleanOlderThan int
var cleanKeep int
var cleanForce bool

var cleanCmd = &cobra.Command{
	Use:   "clean [logs|db|all]",
	Short: "Clean up historical logs and database records",
	Long: `Remove old logs and database records. Supports cleaning by age or
keeping only a certain number of recent records.

Examples:
  ppsctl clean all --force
  ppsctl clean logs --older-than 7
  ppsctl clean db --keep 100
`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cleanType := args[0]

		if cleanType == "logs" || cleanType == "all" {
			result, err := apiClient.CleanRuns(cleanOlderThan, 0, false)
			if err != nil {
				return fmt.Errorf("failed to clean logs: %w", err)
			}
			color.Green("Deleted %d runs and %d log files\n", result.DeletedRuns, result.DeletedLogs)
		}

		if cleanType == "db" || cleanType == "all" {
			result, err := apiClient.CleanRuns(0, cleanKeep, cleanForce)
			if err != nil {
				return fmt.Errorf("failed to clean database: %w", err)
			}
			color.Green("Deleted %d runs and %d log files\n", result.DeletedRuns, result.DeletedLogs)
		}

		if cleanForce {
			fmt.Println("Cleanup completed.")
		}

		return nil
	},
}

func init() {
	cleanCmd.Flags().IntVar(&cleanOlderThan, "older-than", 0, "delete runs older than N days")
	cleanCmd.Flags().IntVar(&cleanKeep, "keep", 100, "keep only N most recent runs")
	cleanCmd.Flags().BoolVar(&cleanForce, "force", false, "force delete all runs")
	RootCmd.AddCommand(cleanCmd)
}
