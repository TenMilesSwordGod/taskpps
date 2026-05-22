package cmd

import (
	"fmt"

	"github.com/fatih/color"
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/config"
)

var serverInfoCmd = &cobra.Command{
	Use:   "server-info",
	Short: "Display backend connection information",
	RunE: func(cmd *cobra.Command, args []string) error {
		health, err := apiClient.HealthCheck()
		if err != nil {
			color.Red("Server: unreachable (%v)", err)
		} else {
			color.Green("Server: %s (status: %s)", config.GetServerAddr(appConfig), health.Status)
		}
		fmt.Printf("Config: %s\n", appConfig.Server.Host)
		fmt.Printf("Port:   %d\n", appConfig.Server.Port)
		return nil
	},
}

func init() {
	RootCmd.AddCommand(serverInfoCmd)
}
