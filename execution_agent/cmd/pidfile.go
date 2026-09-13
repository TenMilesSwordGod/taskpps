package cmd

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"syscall"
)

// defaultPidFile 是 run/status/stop 共用的默认 PID 文件路径。
const defaultPidFile = "/var/run/taskpps-agent.pid"

// errPIDFileInvalid 标记"文件读到了但内容不是合法 PID"。
// 单独定义是为了让调用方区分"文件不存在/无权限"与"内容无效"两类错误。
var errPIDFileInvalid = errors.New("PID 文件内容无效")

// readPIDFile 读取并解析 PID 文件，空文件/非法内容返回错误而不是 panic。
// 注意(2026-09): 原 status/stop 直接切片 data[:len(data)-1]，空文件会越界 panic；
// 这里统一在入口处校验，避免调用方重复实现截断逻辑。
func readPIDFile(pidFile string) (int, error) {
	data, err := os.ReadFile(pidFile)
	if err != nil {
		// 保留原始错误，便于调用方用 errors.Is 判断文件不存在
		return 0, err
	}

	raw := strings.TrimSpace(string(data))
	if raw == "" {
		return 0, fmt.Errorf("%w: %s 为空", errPIDFileInvalid, pidFile)
	}

	parsed, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("%w: %s 内容 %q 不是数字", errPIDFileInvalid, pidFile, raw)
	}
	return parsed, nil
}

// processIsRunning 通过 signal 0 做存在性/权限检查（不会真正投递信号）。
func processIsRunning(pid int) bool {
	process, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	return process.Signal(syscall.Signal(0)) == nil
}

// checkInstanceRunning reports whether a taskpps-agent daemon is already
// running, as recorded in pidFile. The returned pid is whatever was last
// written to the file (0 if the file is missing or unparseable).
//
// Stale PID files (process no longer exists) are treated as "not running"
// so that the next start can overwrite them cleanly.
func checkInstanceRunning(pidFile string) (running bool, pid int, err error) {
	parsed, err := readPIDFile(pidFile)
	if err != nil {
		// 文件不存在或内容无效都视为未运行，让下一次 start 可以覆盖；
		// 其他读取错误（如权限不足）仍然向上返回，避免掩盖真实问题。
		if errors.Is(err, os.ErrNotExist) || errors.Is(err, errPIDFileInvalid) {
			return false, 0, nil
		}
		return false, 0, fmt.Errorf("read pid file %s: %w", pidFile, err)
	}

	// 如果是当前进程自身（daemon 模式下子进程在父进程写入 PID 文件后
	// 立即检查实例，会出现 TOCTOU 竞态），不视为已有实例运行。
	if parsed == os.Getpid() {
		return false, 0, nil
	}

	if !processIsRunning(parsed) {
		return false, parsed, nil
	}
	return true, parsed, nil
}
