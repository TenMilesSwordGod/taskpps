package cmd

import (
	"errors"
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var statusPidFile string

// statusReport 返回状态提示与建议退出码。
// 抽成纯函数的原因：RunE 里直接 os.Exit 会导致判定逻辑无法被测试，
// 而"三种未运行提示 + 退出码 1 / 运行中退出码 0"是用户可见行为。
func statusReport(pidFile string) (message string, exitCode int) {
	pid, err := readPIDFile(pidFile)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return "taskpps-agent 未运行 (PID 文件不存在)", 1
		}
		// 包含空文件/非法内容等 errPIDFileInvalid 情况
		return "taskpps-agent 未运行 (PID 文件无效)", 1
	}

	if !processIsRunning(pid) {
		return "taskpps-agent 未运行 (进程不存在)", 1
	}
	return fmt.Sprintf("taskpps-agent 正在运行 (PID: %d)", pid), 0
}

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "查看 taskpps-agent 运行状态",
	Long:  "通过 PID 文件检查 taskpps-agent 是否正在运行",
	RunE: func(cmd *cobra.Command, args []string) error {
		if statusPidFile == "" {
			statusPidFile = defaultPidFile
		}

		message, exitCode := statusReport(statusPidFile)
		fmt.Println(message)
		if exitCode != 0 {
			os.Exit(exitCode)
		}
		return nil
	},
}

func init() {
	statusCmd.Flags().StringVar(&statusPidFile, "pid-file", defaultPidFile, "PID 文件路径")
	RootCmd.AddCommand(statusCmd)
}
