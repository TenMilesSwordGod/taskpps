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

		var pythonCmd *exec.Cmd
		if _, err := exec.LookPath("uv"); err == nil {
			pythonCmd = exec.Command("uv", "run", "python", "-m", "taskpps")
		} else {
			pythonExe := "python3"
			if _, err := exec.LookPath(pythonExe); err != nil {
				pythonExe = "python"
			}
			pythonCmd = exec.Command(pythonExe, "-m", "taskpps")
		}

		pythonCmd.Stdout = os.Stdout
		pythonCmd.Stderr = os.Stderr
		pythonCmd.Env = append(os.Environ(), "NO_PROXY=127.0.0.1,localhost")

		if err := pythonCmd.Run(); err != nil {
			return fmt.Errorf("server exited with error: %w", err)
		}
		return nil
	},
}

func init() {
	RootCmd.AddCommand(startServerCmd)
}
