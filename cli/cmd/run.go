package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/tui"
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
			return tui.StartWatch(apiClient, run.ID)
		}

		if run.Status == "running" || run.Status == "pending" {
			fmt.Printf("Use 'ppsctl watch %s' to monitor progress.\n", run.ID)
		}
		return nil
	},
}

func colorForStatus(s string) *color.Color {
	switch s {
	case "running", "pending":
		return color.New(color.FgYellow)
	case "success":
		return color.New(color.FgGreen)
	case "failed":
		return color.New(color.FgRed)
	case "cancelled":
		return color.New(color.FgMagenta)
	case "skipped":
		return color.New(color.FgHiBlack)
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
		return color.New(color.FgHiBlack)
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