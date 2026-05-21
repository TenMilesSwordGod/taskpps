package cmd

import (
	"fmt"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/client"
)

var runParams []string
var runWatch bool
var runDetach bool

var runCmd = &cobra.Command{
	Use:   "run <pipeline-file>",
	Short: "Submit a pipeline run",
	Long: `Submit a pipeline YAML file for execution. Supports parameter overrides
with -p flag and optional foreground monitoring with --watch.

Examples:
  ppsctl run deploy.yaml
  ppsctl run deploy.yaml -p "options.host=prod-server"
  ppsctl run deploy.yaml --watch
  ppsctl run deploy.yaml --detach
`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		pipelineFile := args[0]
		params := client.ParseParams(runParams)

		color.Cyan("Submitting pipeline: %s\n", pipelineFile)

		run, err := apiClient.CreateRun(pipelineFile, params)
		if err != nil {
			return fmt.Errorf("failed to submit run: %w", err)
		}

		color.Green("Run created: %s (status: %s)\n", run.ID, run.Status)

		if runDetach {
			fmt.Printf("Run %s is running in background.\n", run.ID)
			fmt.Printf("Use 'ppsctl logs %s' to view logs.\n", run.ID)
			fmt.Printf("Use 'ppsctl watch %s' to attach to it.\n", run.ID)
			return nil
		}

		if runWatch {
			return watchRun(run.ID)
		}

		if run.Status == "running" || run.Status == "pending" {
			fmt.Printf("Use 'ppsctl watch %s' to monitor progress.\n", run.ID)
		}
		return nil
	},
}

func watchRun(runID string) error {
	color.Cyan("Monitoring run %s (Ctrl+C to stop)\n", runID)

	lastStatus := ""
	for {
		run, err := apiClient.GetRun(runID)
		if err != nil {
			return err
		}

		if run.Status != lastStatus {
			statusColor := colorForStatus(string(run.Status))
			statusColor.Printf("Status: %s\n", run.Status)
			lastStatus = run.Status
		}

		for _, task := range run.Tasks {
			taskColor := colorForTaskStatus(string(task.Status))
			taskColor.Printf("  [%s] %s", task.Status, task.TaskName)
			if task.FinishedAt != nil {
				fmt.Printf(" (done)")
			}
			fmt.Println()
		}

		if run.Status == "success" {
			color.Green("\nPipeline completed successfully!\n")
			return nil
		}
		if run.Status == "failed" || run.Status == "cancelled" || run.Status == "partial" {
			color.Red("\nPipeline finished with status: %s\n", run.Status)
			return nil
		}

		time.Sleep(2 * time.Second)
	}
}

func colorForStatus(s string) *color.Color {
	switch s {
	case "running", "pending":
		return color.New(color.FgYellow)
	case "success":
		return color.New(color.FgGreen)
	case "failed", "cancelled":
		return color.New(color.FgRed)
	default:
		return color.New(color.FgWhite)
	}
}

func colorForTaskStatus(s string) *color.Color {
	switch s {
	case "running", "pending":
		return color.New(color.FgYellow)
	case "success":
		return color.New(color.FgGreen)
	case "failed":
		return color.New(color.FgRed)
	case "skipped":
		return color.New(color.FgCyan)
	case "cancelled":
		return color.New(color.FgMagenta)
	default:
		return color.New(color.FgWhite)
	}
}

func init() {
	runCmd.Flags().StringArrayVarP(&runParams, "param", "p", nil, "parameter override (e.g. -p options.host=prod)")
	runCmd.Flags().BoolVar(&runWatch, "watch", false, "watch run in foreground after submission")
	runCmd.Flags().BoolVar(&runDetach, "detach", false, "submit and run in background")
	RootCmd.AddCommand(runCmd)
}
