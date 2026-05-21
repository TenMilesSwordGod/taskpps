package cmd

import (
	"fmt"
	"os"

	"github.com/fatih/color"
	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/models"
)

var triggerType string
var triggerConfig string
var triggerPipeline string
var triggerEnabled bool

var triggerCmd = &cobra.Command{
	Use:   "trigger [add|list|delete]",
	Short: "Manage pipeline triggers",
	Long: `Manage cron and webhook triggers for pipeline execution.

Examples:
  ppsctl trigger add --type cron --config '{"schedule":"0 2 * * *"}' --pipeline nightly.yaml
  ppsctl trigger list
  ppsctl trigger delete <trigger-id>
`,
}

var triggerAddCmd = &cobra.Command{
	Use:   "add",
	Short: "Add a new trigger",
	RunE: func(cmd *cobra.Command, args []string) error {
		reqBody := models.CreateTriggerRequest{
			Type:         triggerType,
			Config:       triggerConfig,
			PipelineFile: triggerPipeline,
			Enabled:      triggerEnabled,
		}

		trigger, err := apiClient.CreateTrigger(reqBody)
		if err != nil {
			return fmt.Errorf("failed to create trigger: %w", err)
		}

		color.Green("Trigger created: %s (type: %s, pipeline: %s)\n", trigger.ID, trigger.Type, trigger.PipelineFile)
		return nil
	},
}

var triggerListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all triggers",
	RunE: func(cmd *cobra.Command, args []string) error {
		triggers, err := apiClient.ListTriggers()
		if err != nil {
			return fmt.Errorf("failed to list triggers: %w", err)
		}

		if len(triggers) == 0 {
			fmt.Println("No triggers configured.")
			return nil
		}

		table := tablewriter.NewWriter(os.Stdout)
		table.SetHeader([]string{"ID", "Type", "Pipeline", "Enabled", "Created"})
		table.SetBorder(false)
		table.SetColumnSeparator(" ")

		for _, t := range triggers {
			enabled := "no"
			if t.Enabled {
				enabled = "yes"
			}
			table.Append([]string{t.ID, t.Type, t.PipelineFile, enabled, t.CreatedAt})
		}

		table.Render()
		return nil
	},
}

var triggerDeleteCmd = &cobra.Command{
	Use:   "delete <trigger-id>",
	Short: "Delete a trigger",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		triggerID := args[0]

		if err := apiClient.DeleteTrigger(triggerID); err != nil {
			return err
		}

		color.Green("Trigger %s deleted.\n", triggerID)
		return nil
	},
}

func init() {
	triggerAddCmd.Flags().StringVar(&triggerType, "type", "", "trigger type (cron, webhook)")
	triggerAddCmd.Flags().StringVar(&triggerConfig, "config", "", "trigger configuration JSON")
	triggerAddCmd.Flags().StringVar(&triggerPipeline, "pipeline", "", "pipeline file to trigger")
	triggerAddCmd.Flags().BoolVar(&triggerEnabled, "enabled", true, "enable the trigger")

	triggerCmd.AddCommand(triggerAddCmd)
	triggerCmd.AddCommand(triggerListCmd)
	triggerCmd.AddCommand(triggerDeleteCmd)
	RootCmd.AddCommand(triggerCmd)
}
