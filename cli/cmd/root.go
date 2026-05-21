package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
)

var (
	cfgFile   string
	apiClient *client.Client
	appConfig *config.Config
)

var RootCmd = &cobra.Command{
	Use:   "ppsctl",
	Short: "taskpps CLI - Lightweight task pipeline system",
	Long: `ppsctl is the command-line interface for taskpps, a lightweight 
task pipeline orchestration system. It communicates with the taskpps 
backend server via REST API.`,
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		if cmd.Name() == "init" {
			return nil
		}
		var err error
		appConfig, err = config.Load(cfgFile)
		if err != nil {
			return fmt.Errorf("failed to load config: %w", err)
		}
		apiClient = client.New(appConfig)
		return nil
	},
	Run: func(cmd *cobra.Command, args []string) {
		cmd.Help()
	},
}

func Execute() {
	if err := RootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func init() {
	RootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "path to taskpps.yaml config file")
	RootCmd.PersistentFlags().StringP("server", "s", "", "server address (host:port)")
}
