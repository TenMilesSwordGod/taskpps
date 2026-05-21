package cmd

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/spf13/cobra"
)

var startServerCmd = &cobra.Command{
	Use:   "start-server",
	Short: "Start the taskpps backend server",
	Long: `Start the Python backend server by running the taskpps Python package.
The server address is configured in taskpps.yaml.`,
	RunE: func(cmd *cobra.Command, args []string) error {
		fmt.Println("Starting taskpps server...")

		pythonCmd := exec.Command("python", "-m", "taskpps")
		pythonCmd.Stdout = os.Stdout
		pythonCmd.Stderr = os.Stderr

		if err := pythonCmd.Run(); err != nil {
			return fmt.Errorf("server exited with error: %w", err)
		}
		return nil
	},
}

func init() {
	RootCmd.AddCommand(startServerCmd)
}
