package cmd

import (
	"errors"
	"fmt"
	"os"
	"syscall"

	"github.com/spf13/cobra"
)

var stopPidFile string

// stopAgent 读取 PID 文件并向目标进程发送 SIGTERM，成功后删除 PID 文件。
// 返回解析到的 pid 供调用方输出提示；错误信息保持原 RunE 的文案。
// 注意(2026-09): 原实现 data[:len(data)-1] 对空文件会 panic，现统一走 readPIDFile。
func stopAgent(pidFile string) (int, error) {
	pid, err := readPIDFile(pidFile)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return 0, fmt.Errorf("无法读取 PID 文件 %s: %w", pidFile, err)
		}
		return 0, fmt.Errorf("无效的 PID 文件内容: %w", err)
	}

	process, err := os.FindProcess(pid)
	if err != nil {
		return 0, fmt.Errorf("找不到进程 %d: %w", pid, err)
	}

	if err := process.Signal(syscall.SIGTERM); err != nil {
		return 0, fmt.Errorf("发送 SIGTERM 到进程 %d 失败: %w", pid, err)
	}

	os.Remove(pidFile)
	return pid, nil
}

var stopCmd = &cobra.Command{
	Use:   "stop",
	Short: "停止 taskpps-agent",
	Long:  "通过 PID 文件停止正在运行的 taskpps-agent daemon",
	RunE: func(cmd *cobra.Command, args []string) error {
		if stopPidFile == "" {
			stopPidFile = defaultPidFile
		}

		pid, err := stopAgent(stopPidFile)
		if err != nil {
			return err
		}

		fmt.Printf("已发送 SIGTERM 到 taskpps-agent (PID: %d)\n", pid)
		return nil
	},
}

func init() {
	stopCmd.Flags().StringVar(&stopPidFile, "pid-file", defaultPidFile, "PID 文件路径")
	RootCmd.AddCommand(stopCmd)
}
