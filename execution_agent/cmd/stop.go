package cmd

import (
	"fmt"
	"os"
	"strconv"
	"syscall"

	"github.com/spf13/cobra"
)

var stopPidFile string

var stopCmd = &cobra.Command{
	Use:   "stop",
	Short: "停止 taskpps-agent",
	Long:  "通过 PID 文件停止正在运行的 taskpps-agent daemon",
	RunE: func(cmd *cobra.Command, args []string) error {
		if stopPidFile == "" {
			stopPidFile = "/var/run/taskpps-agent.pid"
		}

		data, err := os.ReadFile(stopPidFile)
		if err != nil {
			return fmt.Errorf("无法读取 PID 文件 %s: %w", stopPidFile, err)
		}

		pid, err := strconv.Atoi(string(data[:len(data)-1]))
		if err != nil {
			return fmt.Errorf("无效的 PID 文件内容: %w", err)
		}

		process, err := os.FindProcess(pid)
		if err != nil {
			return fmt.Errorf("找不到进程 %d: %w", pid, err)
		}

		if err := process.Signal(syscall.SIGTERM); err != nil {
			return fmt.Errorf("发送 SIGTERM 到进程 %d 失败: %w", pid, err)
		}

		fmt.Printf("已发送 SIGTERM 到 taskpps-agent (PID: %d)\n", pid)
		os.Remove(stopPidFile)
		return nil
	},
}

func init() {
	stopCmd.Flags().StringVar(&stopPidFile, "pid-file", "/var/run/taskpps-agent.pid", "PID 文件路径")
	RootCmd.AddCommand(stopCmd)
}
