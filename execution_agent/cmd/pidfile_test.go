package cmd

import (
	"os"
	"path/filepath"
	"strconv"
	"testing"
)

func TestCheckInstanceRunning_NoPidFile(t *testing.T) {
	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")

	running, pid, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if running {
		t.Fatalf("expected running=false when pid file is missing")
	}
	if pid != 0 {
		t.Fatalf("expected pid=0 when pid file is missing, got %d", pid)
	}
}

func TestCheckInstanceRunning_EmptyPidFile(t *testing.T) {
	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	if err := os.WriteFile(pidFile, []byte("\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, _, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if running {
		t.Fatalf("expected running=false for empty pid file")
	}
}

func TestCheckInstanceRunning_GarbagePidFile(t *testing.T) {
	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	if err := os.WriteFile(pidFile, []byte("not-a-number\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, _, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if running {
		t.Fatalf("expected running=false for unparseable pid file")
	}
}

func TestCheckInstanceRunning_StalePidFile(t *testing.T) {
	// PID 0 is special on Linux: signaling it always returns ESRCH or EPERM
	// from inside the same process group, so a regular non-existent PID
	// is the cleanest way to simulate a stale file. We use a high number
	// that is very unlikely to be assigned.
	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	stale := 9_999_999
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(stale)+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, pid, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if running {
		t.Fatalf("expected running=false for stale pid file (PID %d does not exist)", stale)
	}
	if pid != stale {
		t.Fatalf("expected pid=%d, got %d", stale, pid)
	}
}

func TestCheckInstanceRunning_CurrentProcess(t *testing.T) {
	// 当 PID 文件中的 PID 就是当前进程自身时（daemon 模式子进程启动时
	// 父进程刚写完 PID 文件会出现），不视为已有实例运行，避免 TOCTOU 竞态。
	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(os.Getpid())+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, pid, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if running {
		t.Fatalf("expected running=false when pid file points to current process (pid %d)", os.Getpid())
	}
	if pid != 0 {
		t.Fatalf("expected pid=0, got %d", pid)
	}
}

func TestCheckInstanceRunning_OtherProcess(t *testing.T) {
	// PID 1 (init) 在 Linux 上总是存在，用于验证非自身进程的检测。
	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	if err := os.WriteFile(pidFile, []byte("1\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, pid, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !running {
		t.Fatalf("expected running=true for PID 1 (init)")
	}
	if pid != 1 {
		t.Fatalf("expected pid=1, got %d", pid)
	}
}
