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
	cfgFile     string
	projectFlag string
	apiClient   *client.Client
	appConfig   *config.Config
	verbose     int
)

var RootCmd = &cobra.Command{
	Use:   "ppsctl",
	Short: "taskpps CLI - Lightweight task pipeline system",
	Long: `ppsctl is the command-line interface for taskpps, a lightweight 
task pipeline orchestration system. It communicates with the taskpps 
backend server via REST API.`,
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		// Map verbose count (-v) to our log levels:
		// 0: LevelNone (no logs anywhere)
		// 1: LevelError
		// 2: LevelWarn
		// 3: LevelInfo
		// 4+: LevelDebug
		logLevel := 0
		if verbose == 1 {
			logLevel = 1
		} else if verbose == 2 {
			logLevel = 2
		} else if verbose == 3 {
			logLevel = 3
		} else if verbose >= 4 {
			logLevel = 4
		}
		logger.SetLevel(logLevel)

		// Only enable console output when verbose flag is set
		if verbose > 0 {
			logger.EnableVerboseOutput()
		}

		if logLevel >= 4 {
			logger.Debug("Verbose level set to %d (logLevel: %d)", verbose, logLevel)
			logger.Debug("Command: %s", cmd.Name())
		}

		if cmd.Name() == "init" || cmd.Name() == "version" {
			return nil
		}
		// 解析 api_key: flag --api-key > env PPSCTL_API_KEY
		if apiKeyFlag := cmd.Flag("api-key"); apiKeyFlag != nil && apiKeyFlag.Value.String() != "" {
			config.ApiKeyOverride = apiKeyFlag.Value.String()
		} else if envKey := os.Getenv("PPSCTL_API_KEY"); envKey != "" {
			config.ApiKeyOverride = envKey
		}
		var err error
		appConfig, err = config.Load(cfgFile, projectFlag)
		if err != nil {
			if verbose >= 1 {
				logger.Error("Failed to load config: %v", err)
			}
			return fmt.Errorf("failed to load config: %w", err)
		}
		if verbose >= 3 {
			logger.Info("Config loaded successfully")
		}
		apiClient = client.New(appConfig)
		if verbose >= 4 {
			logger.Debug("API client initialized")
		}

		// Check version mismatch
		health, err := apiClient.HealthCheck()
		if err == nil && health != nil {
			if verbose >= 4 {
				logger.Debug("Server version: %s", health.Version)
			}
			CheckVersionMismatch(health.Version)
		} else if err != nil {
			if verbose >= 2 {
				logger.Warn("Could not check server version: %v", err)
			}
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
	RootCmd.PersistentFlags().StringVarP(&projectFlag, "project", "P", "", "项目工作目录路径")
	RootCmd.PersistentFlags().StringP("server", "s", "", "server address (host:port)")
	RootCmd.PersistentFlags().StringP("api-key", "k", "", "API key for server authentication (overrides config file and PPSCTL_API_KEY env)")
	RootCmd.PersistentFlags().CountVarP(&verbose, "verbose", "v", "increase verbosity (-v: warn, -vv: info, -vvv: debug)")
}
