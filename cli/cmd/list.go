package cmd

import (
	"fmt"
	"os"

	"github.com/fatih/color"
	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"
)

var listPipeline string
var listStatus string
var listLimit int

var listCmd = &cobra.Command{
	Use:   "list",
	Short: "List pipeline run history",
	Long: `Display a table of all pipeline runs with filtering by pipeline name and status.

Examples:
  ppsctl list
  ppsctl list --pipeline deploy
  ppsctl list --status failed
  ppsctl list --limit 20
`,
	RunE: func(cmd *cobra.Command, args []string) error {
		runs, err := apiClient.ListRuns(listPipeline, listStatus, listLimit)
		if err != nil {
			return fmt.Errorf("failed to list runs: %w", err)
		}

		if len(runs.Items) == 0 {
			fmt.Println("No runs found.")
			return nil
		}

		table := tablewriter.NewWriter(os.Stdout)
		table.SetHeader([]string{"ID", "Pipeline", "Status", "Started", "Finished"})
		table.SetBorder(false)
		table.SetColumnSeparator(" ")
		table.SetAutoWrapText(false)

		for _, run := range runs.Items {
			started := ""
			if run.StartedAt != nil {
				started = *run.StartedAt
			}
			finished := ""
			if run.FinishedAt != nil {
				finished = *run.FinishedAt
			}

			statusStr := string(run.Status)
			statusColor := colorForStatus(string(run.Status))
			statusStr = statusColor.Sprint(statusStr)

			table.Append([]string{
				run.ID,
				run.PipelineName,
				statusStr,
				started,
				finished,
			})
		}

		table.Render()
		fmt.Printf("\nTotal: %d runs\n", runs.Total)
		return nil
	},
}

func init() {
	listCmd.Flags().StringVar(&listPipeline, "pipeline", "", "filter by pipeline name")
	listCmd.Flags().StringVar(&listStatus, "status", "", "filter by status (running/success/failed/cancelled)")
	listCmd.Flags().IntVar(&listLimit, "limit", 50, "max number of runs to show")
	RootCmd.AddCommand(listCmd)
}
