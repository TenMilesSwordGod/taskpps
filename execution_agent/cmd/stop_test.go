package cmd

import (
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
)

// TestStopAgent_InvalidPidFiles 覆盖空文件/缺文件/非法内容的错误语义。
// 空文件是回归用例：原实现 data[:len(data)-1] 会对空切片 panic。
func TestStopAgent_InvalidPidFiles(t *testing.T) {
	t.Run("missing file", func(t *testing.T) {
		_, err := stopAgent(filepath.Join(t.TempDir(), "missing.pid"))
		if err == nil {
			t.Fatal("expected error for missing pid file")
		}
		if !strings.Contains(err.Error(), "无法读取 PID 文件") {
			t.Errorf("error = %v, want readable message", err)
		}
	})

	t.Run("empty file", func(t *testing.T) {
		pidFile := filepath.Join(t.TempDir(), "empty.pid")
		if err := os.WriteFile(pidFile, []byte(""), 0o644); err != nil {
			t.Fatalf("write pid file: %v", err)
		}
		_, err := stopAgent(pidFile)
		if err == nil {
			t.Fatal("expected error for empty pid file (must not panic)")
		}
		if !strings.Contains(err.Error(), "无效的 PID 文件内容") {
			t.Errorf("error = %v, want invalid-content message", err)
		}
	})

	t.Run("garbage content", func(t *testing.T) {
		pidFile := filepath.Join(t.TempDir(), "garbage.pid")
		if err := os.WriteFile(pidFile, []byte("abc\n"), 0o644); err != nil {
			t.Fatalf("write pid file: %v", err)
		}
		if _, err := stopAgent(pidFile); err == nil {
			t.Fatal("expected error for non-numeric pid file")
		}
	})
}

// TestStopAgent_SignalsProcessAndRemovesPidFile 用真实子进程验证 stop 的用户可见行为：
// 目标进程收到 SIGTERM，成功后 PID 文件被删除。
func TestStopAgent_SignalsProcessAndRemovesPidFile(t *testing.T) {
	child := exec.Command("sleep", "30")
	if err := child.Start(); err != nil {
		t.Fatalf("启动子进程失败: %v", err)
	}
	t.Cleanup(func() {
		if child.ProcessState == nil {
			_ = child.Process.Kill()
			_, _ = child.Process.Wait()
		}
	})

	pidFile := filepath.Join(t.TempDir(), "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(child.Process.Pid)+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	pid, err := stopAgent(pidFile)
	if err != nil {
		t.Fatalf("stopAgent() error: %v", err)
	}
	if pid != child.Process.Pid {
		t.Errorf("stopAgent() pid = %d, want %d", pid, child.Process.Pid)
	}

	waitErr := child.Wait()
	var exitErr *exec.ExitError
	if !errors.As(waitErr, &exitErr) {
		t.Fatalf("expected child to be signaled, got wait error: %v", waitErr)
	}
	if ws := exitErr.Sys().(syscall.WaitStatus); !ws.Signaled() || ws.Signal() != syscall.SIGTERM {
		t.Errorf("child wait status = %v, want SIGTERM", exitErr.Sys())
	}

	if _, err := os.Stat(pidFile); !os.IsNotExist(err) {
		t.Errorf("pid file should be removed after stop, stat err = %v", err)
	}
}

// TestStopAgent_StaleProcess 验证目标进程不存在时返回可读错误。
func TestStopAgent_StaleProcess(t *testing.T) {
	pidFile := filepath.Join(t.TempDir(), "agent.pid")
	if err := os.WriteFile(pidFile, []byte("9999999\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	if _, err := stopAgent(pidFile); err == nil {
		t.Fatal("expected error when target process does not exist")
	}
}
