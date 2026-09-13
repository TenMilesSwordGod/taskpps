package cmd

import (
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"testing"
)

// startControlledProcess 启动一个由测试控制生命周期的真实子进程。
// 为什么不用 PID 1：非 root 用户对 PID 1 执行 signal 0 会返回 EPERM，
// 被生产逻辑判为"未运行"，导致用例在普通开发机上恒失败（审计报告根因）。
func startControlledProcess(t *testing.T, command ...string) *exec.Cmd {
	t.Helper()
	cmd := exec.Command(command[0], command[1:]...)
	if err := cmd.Start(); err != nil {
		t.Fatalf("启动测试子进程 %v 失败: %v", command, err)
	}
	t.Cleanup(func() {
		// 已 Wait 过（进程自然退出）就不再重复回收，避免干扰退出语义测试
		if cmd.ProcessState == nil {
			_ = cmd.Process.Kill()
			_, _ = cmd.Process.Wait()
		}
	})
	return cmd
}

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
	// 用真实受控子进程验证"非自身进程"判定，替代原先硬编码 PID 1 的写法。
	child := startControlledProcess(t, "sleep", "30")
	childPID := child.Process.Pid

	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(childPID)+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, pid, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !running {
		t.Fatalf("expected running=true for live child pid %d", childPID)
	}
	if pid != childPID {
		t.Fatalf("expected pid=%d, got %d", childPID, pid)
	}
}

func TestCheckInstanceRunning_ExitedProcess(t *testing.T) {
	// 判定语义的双向完整性：进程退出并被回收后必须判为未运行。
	child := startControlledProcess(t, "sh", "-c", "exit 0")
	childPID := child.Process.Pid
	if err := child.Wait(); err != nil {
		t.Fatalf("等待子进程退出失败: %v", err)
	}

	dir := t.TempDir()
	pidFile := filepath.Join(dir, "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(childPID)+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	running, pid, err := checkInstanceRunning(pidFile)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if running {
		t.Fatalf("expected running=false after child %d exited", childPID)
	}
	if pid != childPID {
		t.Fatalf("expected stale pid=%d, got %d", childPID, pid)
	}
}
