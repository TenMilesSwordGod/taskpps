package cmd

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// TestStatusReport_FailureStates 覆盖 status 的三种"未运行"提示与退出码 1。
// 空文件是回归用例：原实现 data[:len(data)-1] 会越界 panic（status.go 修复前）。
func TestStatusReport_FailureStates(t *testing.T) {
	tests := []struct {
		name        string
		content     []byte
		wantMessage string
	}{
		{"missing file", nil, "PID 文件不存在"},
		{"empty file", []byte(""), "PID 文件无效"},
		{"newline only", []byte("\n"), "PID 文件无效"},
		{"garbage content", []byte("not-a-pid\n"), "PID 文件无效"},
		{"stale process", []byte("9999999\n"), "进程不存在"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			pidFile := filepath.Join(t.TempDir(), "agent.pid")
			if tt.content != nil {
				if err := os.WriteFile(pidFile, tt.content, 0o644); err != nil {
					t.Fatalf("write pid file: %v", err)
				}
			}

			message, exitCode := statusReport(pidFile)
			if exitCode != 1 {
				t.Errorf("exitCode = %d, want 1", exitCode)
			}
			if !strings.Contains(message, "未运行") || !strings.Contains(message, tt.wantMessage) {
				t.Errorf("message = %q, want it to contain %q", message, tt.wantMessage)
			}
		})
	}
}

// TestStatusReport_RunningProcess 覆盖运行中状态的提示与退出码 0。
func TestStatusReport_RunningProcess(t *testing.T) {
	pidFile := filepath.Join(t.TempDir(), "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(os.Getpid())+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	message, exitCode := statusReport(pidFile)
	if exitCode != 0 {
		t.Fatalf("exitCode = %d, want 0 (message=%q)", exitCode, message)
	}
	if !strings.Contains(message, "正在运行") || !strings.Contains(message, strconv.Itoa(os.Getpid())) {
		t.Errorf("message = %q, want running state with pid %d", message, os.Getpid())
	}
}
