package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/logger"
)

var (
	cfgFile   string
	apiClient *client.Client
	appConfig *config.Config
	verbose int
)

var RootCmd = &cobra.Command{
	Use:   "ppsctl",
	Short: "taskpps CLI - Lightweight task pipeline system",
	Long: `ppsctl is the command-line interface for taskpps, a lightweight 
task pipeline orchestration system. It communicates with the taskpps 
backend server via REST API.`,
	PersistentPreRun: func(cmd *cobra.Command, args []string) {
		logger.SetLevel(verbose)
		logger.Debug("Verbose level set to %d", verbose)
		logger.Debug("Command: %s", cmd.Name())
	},
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		if cmd.Name() == "init" || cmd.Name() == "version" {
			return nil
		}
		var err error
		appConfig, err = config.Load(cfgFile)
		if err != nil {
			logger.Error("Failed to load config: %v", err)
			return fmt.Errorf("failed to load config: %w", err)
		}
		logger.Info("Config loaded successfully")
		apiClient = client.New(appConfig)
		logger.Debug("API client initialized")
		
		// 检查版本匹配
		health, err := apiClient.HealthCheck()
		if err == nil && health != nil {
			logger.Debug("Server version: %s", health.Version)
			CheckVersionMismatch(health.Version)
		} else if err != nil {
			logger.Warn("Could not check server version: %v", err)
		}
		
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
	RootCmd.PersistentFlags().CountVarP(&verbose, "verbose", "v", "increase verbosity (-v: warn, -vv: info, -vvv: debug)")
}
