package cmd

import (
	"fmt"
	"os"

	"github.com/fatih/color"
	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"
)

var statusCmd = &cobra.Command{
	Use:   "status <run-id>",
	Short: "Show detailed run status",
	Long: `Display detailed information about a specific pipeline run, including
all task statuses and timing.

Example:
  ppsctl status abc123def456
`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		runID := args[0]

		run, err := apiClient.GetRun(runID)
		if err != nil {
			return err
		}

		color.Cyan("Run: %s\n", run.ID)
		fmt.Printf("  Pipeline:  %s\n", run.PipelineName)
		fmt.Printf("  File:      %s\n", run.PipelineFile)

		statusColor := colorForStatus(string(run.Status))
		statusColor.Printf("  Status:    %s\n", run.Status)

		if run.StartedAt != nil {
			fmt.Printf("  Started:   %s\n", *run.StartedAt)
		}
		if run.FinishedAt != nil {
			fmt.Printf("  Finished:  %s\n", *run.FinishedAt)
		}
		fmt.Printf("  Created:   %s\n", run.CreatedAt)
		fmt.Println()

		if len(run.Tasks) == 0 {
			fmt.Println("No task information available.")
			return nil
		}

		table := tablewriter.NewWriter(os.Stdout)
		table.SetHeader([]string{"Task", "Type", "Status", "Exit Code", "Started", "Finished"})
		table.SetBorder(false)
		table.SetColumnSeparator(" ")
		table.SetAutoWrapText(false)

		for _, task := range run.Tasks {
			exitCode := "-"
			if task.ExitCode != nil {
				exitCode = fmt.Sprintf("%d", *task.ExitCode)
			}
			started := ""
			if task.StartedAt != nil {
				started = *task.StartedAt
			}
			finished := ""
			if task.FinishedAt != nil {
				finished = *task.FinishedAt
			}

			statusStr := colorForTaskStatus(string(task.Status)).Sprint(string(task.Status))

			table.Append([]string{
				task.TaskName,
				task.TaskType,
				statusStr,
				exitCode,
				started,
				finished,
			})
		}

		table.Render()
		return nil
	},
}

func init() {
	RootCmd.AddCommand(statusCmd)
}
