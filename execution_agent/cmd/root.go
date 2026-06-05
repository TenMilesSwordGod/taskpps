package cmd

import (
	"github.com/spf13/cobra"
)

var RootCmd = &cobra.Command{
	Use:   "taskpps-agent",
	Short: "taskpps Execution Agent - Remote command execution agent",
	Long: `taskpps-agent is a lightweight execution agent for the taskpps pipeline system.
It connects to a taskpps server via WebSocket and executes commands locally.`,
	Run: func(cmd *cobra.Command, args []string) {
		cmd.Help()
	},
}
