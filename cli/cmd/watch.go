package cmd

import (
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/models"
)

var watchCmd = &cobra.Command{
	Use:   "watch <run-id>",
	Short: "Monitor a run in the foreground",
	Long: `Attach to and monitor a running pipeline in the foreground with
real-time status updates.

Example:
  ppsctl watch abc123def456
`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		runID := args[0]

		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

		ticker := time.NewTicker(2 * time.Second)
		defer ticker.Stop()

		color.Cyan("Watching run %s (Ctrl+C to stop)\n\n", runID)

		for {
			select {
			case <-sigCh:
				fmt.Println("\nStopped watching.")
				return nil
			case <-ticker.C:
				run, err := apiClient.GetRun(runID)
				if err != nil {
					return err
				}
				renderRunStatus(run)
			}
		}
	},
}

func renderRunStatus(run *models.Run) {
	fmt.Print("\033[H\033[2J")

	b := &strings.Builder{}

	titleColor := color.New(color.FgCyan, color.Bold)
	titleColor.Fprintf(b, " Run: %s (%s)\n", run.ID, run.PipelineName)
	fmt.Fprint(b, " ───────────────────────────────────────\n")

	statusColor := colorForStatus(string(run.Status))
	statusColor.Fprintf(b, " Status: %s\n", run.Status)
	if run.StartedAt != nil {
		fmt.Fprintf(b, " Started: %s\n", *run.StartedAt)
	}
	if run.FinishedAt != nil {
		fmt.Fprintf(b, " Finished: %s\n", *run.FinishedAt)
	}
	fmt.Fprintln(b)

	for _, task := range run.Tasks {
		taskColor := colorForTaskStatus(string(task.Status))

		bar := renderProgressBar(string(task.Status), 20)
		taskColor.Fprintf(b, " %s %s %s\n", taskStatusIcon(string(task.Status)), task.TaskName, bar)

		started := ""
		if task.StartedAt != nil {
			started = *task.StartedAt
		}
		if started != "" {
			fmt.Fprintf(b, "    Started: %s", started)
			if task.FinishedAt != nil {
				fmt.Fprintf(b, " Finished: %s", *task.FinishedAt)
			}
			fmt.Fprintln(b)
		}
	}

	if run.Status == "success" || run.Status == "failed" ||
		run.Status == "cancelled" || run.Status == "partial" {
		fmt.Fprintln(b)
		doneColor := color.New(color.FgGreen)
		if run.Status != "success" {
			doneColor = color.New(color.FgRed)
		}
		doneColor.Fprintf(b, " Pipeline finished with status: %s\n", run.Status)
		fmt.Fprint(b, " Press Ctrl+C to exit.\n")
	}

	os.Stdout.WriteString(b.String())
}

func taskStatusIcon(s string) string {
	switch s {
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

func renderProgressBar(status string, width int) string {
	switch status {
	case "running":
		return color.New(color.FgYellow).Sprintf("[%s%s]", strings.Repeat("█", width/2), strings.Repeat("░", width/2))
	case "success":
		return color.New(color.FgGreen).Sprintf("[%s]", strings.Repeat("█", width))
	case "failed":
		return color.New(color.FgRed).Sprintf("[%s]", strings.Repeat("█", width))
	case "pending":
		return color.New(color.FgWhite).Sprintf("[%s]", strings.Repeat("░", width))
	case "skipped", "cancelled":
		return color.New(color.FgCyan).Sprintf("[%s]", strings.Repeat("─", width))
	default:
		return ""
	}
}

func init() {
	RootCmd.AddCommand(watchCmd)
}
