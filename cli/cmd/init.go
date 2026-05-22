package cmd

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/spf13/cobra"
)

var initCmd = &cobra.Command{
	Use:   "init",
	Short: "Initialize project directory structure",
	Long: `Create the default project directory structure and sample configuration files
for a taskpps project in the current directory.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		dirs := []string{
			"pipelines",
			"tasks",
			"agents",
			"credentials",
			"plugins",
			".taskpps",
		}
		for _, d := range dirs {
			path := filepath.Join(".", d)
			if err := os.MkdirAll(path, 0755); err != nil {
				return fmt.Errorf("failed to create %s: %w", d, err)
			}
			fmt.Printf("  created %s/\n", d)
		}

		taskppsYAML := `server:
  host: 127.0.0.1
  port: 26521
executor:
  default_timeout: 3600
  max_workers: 10
  shell: /bin/bash
env:
  GLOBAL_VAR: value
plugins:
  paths: ["plugins"]
triggers: []
`
		configPath := filepath.Join(".taskpps", "taskpps.yaml")
		if err := os.WriteFile(configPath, []byte(taskppsYAML), 0644); err != nil {
			return fmt.Errorf("failed to write %s: %w", configPath, err)
		}
		fmt.Println("  created .taskpps/taskpps.yaml")

		pipelineYAML := `name: example
options:
  host: localhost
  env:
    APP_ENV: development
  timeout: 600
  on_failure: fail

tasks:
  - name: build
    command: echo "building..."
  - name: test
    command: echo "running tests..."
    depends_on: [build]
  - name: deploy
    command: echo "deploying..."
    depends_on: [test]
`
		if err := os.WriteFile(filepath.Join("pipelines", "example.yaml"), []byte(pipelineYAML), 0644); err != nil {
			return fmt.Errorf("failed to write example pipeline: %w", err)
		}
		fmt.Println("  created pipelines/example.yaml")

		credYAML := `password: changeme
`
		if err := os.WriteFile(filepath.Join("credentials", "default.yaml"), []byte(credYAML), 0644); err != nil {
			return fmt.Errorf("failed to write default credential: %w", err)
		}
		fmt.Println("  created credentials/default.yaml")

		agentYAML := `host: 127.0.0.1
port: 22
username: deploy
`
		if err := os.WriteFile(filepath.Join("agents", "local.yaml"), []byte(agentYAML), 0644); err != nil {
			return fmt.Errorf("failed to write default agent: %w", err)
		}
		fmt.Println("  created agents/local.yaml")

		fmt.Println("\nProject initialized successfully!")
		return nil
	},
}

func init() {
	RootCmd.AddCommand(initCmd)
}
