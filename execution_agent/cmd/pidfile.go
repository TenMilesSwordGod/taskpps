package cmd

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"syscall"
)

// checkInstanceRunning reports whether a taskpps-agent daemon is already
// running, as recorded in pidFile. The returned pid is whatever was last
// written to the file (0 if the file is missing or unparseable).
//
// Stale PID files (process no longer exists) are treated as "not running"
// so that the next start can overwrite them cleanly.
func checkInstanceRunning(pidFile string) (running bool, pid int, err error) {
	data, err := os.ReadFile(pidFile)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return false, 0, nil
		}
		return false, 0, fmt.Errorf("read pid file %s: %w", pidFile, err)
	}

	raw := strings.TrimSpace(string(data))
	if raw == "" {
		return false, 0, nil
	}

	parsed, err := strconv.Atoi(raw)
	if err != nil {
		// Garbage in the PID file: treat as no running instance so the
		// caller can overwrite it.
		return false, 0, nil
	}

	// 如果是当前进程自身（daemon 模式下子进程在父进程写入 PID 文件后
	// 立即检查实例，会出现 TOCTOU 竞态），不视为已有实例运行。
	if parsed == os.Getpid() {
		return false, 0, nil
	}

	process, err := os.FindProcess(parsed)
	if err != nil {
		return false, parsed, nil
	}

	// Signal 0 does not actually deliver a signal; it only performs the
	// existence / permission check. ESRCH means the process is gone.
	if sigErr := process.Signal(syscall.Signal(0)); sigErr != nil {
		return false, parsed, nil
	}

	return true, parsed, nil
}
