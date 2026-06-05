package cmd

import (
	"fmt"
	"os"
	"strconv"
	"syscall"

	"github.com/spf13/cobra"
)

var statusPidFile string

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "查看 taskpps-agent 运行状态",
	Long:  "通过 PID 文件检查 taskpps-agent 是否正在运行",
	RunE: func(cmd *cobra.Command, args []string) error {
		if statusPidFile == "" {
			statusPidFile = "/var/run/taskpps-agent.pid"
		}

		data, err := os.ReadFile(statusPidFile)
		if err != nil {
			fmt.Println("taskpps-agent 未运行 (PID 文件不存在)")
			os.Exit(1)
			return nil
		}

		pid, err := strconv.Atoi(string(data[:len(data)-1]))
		if err != nil {
			fmt.Println("taskpps-agent 未运行 (PID 文件无效)")
			os.Exit(1)
			return nil
		}

		process, err := os.FindProcess(pid)
		if err != nil {
			fmt.Println("taskpps-agent 未运行 (找不到进程)")
			os.Exit(1)
			return nil
		}

		if err := process.Signal(syscall.Signal(0)); err != nil {
			fmt.Println("taskpps-agent 未运行 (进程不存在)")
			os.Exit(1)
			return nil
		}

		fmt.Printf("taskpps-agent 正在运行 (PID: %d)\n", pid)
		return nil
	},
}

func init() {
	statusCmd.Flags().StringVar(&statusPidFile, "pid-file", "/var/run/taskpps-agent.pid", "PID 文件路径")
	RootCmd.AddCommand(statusCmd)
}
