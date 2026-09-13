package agent

import (
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

// TestKillProcessTree 用真实进程树验证 killProcessTree：
// sh 拉起 sleep 后 wait，killProcessTree 必须把 sh 及其后代 sleep 一并杀掉。
func TestKillProcessTree(t *testing.T) {
	pidFile := filepath.Join(t.TempDir(), "descendant.pid")
	cmd := exec.Command("/bin/sh", "-c", "sleep 30 & echo $! > "+pidFile+"; wait")
	if err := cmd.Start(); err != nil {
		t.Fatalf("启动进程树失败: %v", err)
	}
	t.Cleanup(func() {
		if cmd.ProcessState == nil {
			_ = cmd.Process.Kill()
			_, _ = cmd.Process.Wait()
		}
	})

	var descendantPID int
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if data, err := os.ReadFile(pidFile); err == nil && len(data) > 0 {
			if pid, err := strconv.Atoi(strings.TrimSpace(string(data))); err == nil {
				descendantPID = pid
				break
			}
		}
		time.Sleep(20 * time.Millisecond)
	}
	if descendantPID == 0 {
		t.Fatal("未能读取后代进程 PID")
	}

	killProcessTree(cmd.Process.Pid, syscall.SIGKILL)

	if err := cmd.Wait(); err == nil {
		t.Error("expected sh parent to be killed by SIGKILL")
	}

	// 等内核完成信号投递与回收（遗孤会被 init 收割为 ESRCH）
	deadline = time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if err := syscall.Kill(descendantPID, 0); err == syscall.ESRCH {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Errorf("descendant process %d still alive after killProcessTree", descendantPID)
}

// TestSignalNameFromState 覆盖"从 WaitStatus 提取信号名"的真实入口：
// signalToString 已有测试，但真正决定 ExecResult.SignalName 的是本函数。
func TestSignalNameFromState(t *testing.T) {
	if got := signalNameFromState(nil); got != "" {
		t.Errorf("signalNameFromState(nil) = %q, want empty", got)
	}

	// 正常退出：无信号
	normal := exec.Command("/bin/sh", "-c", "exit 0")
	if err := normal.Run(); err != nil {
		t.Fatalf("run normal exit command: %v", err)
	}
	if got := signalNameFromState(normal.ProcessState); got != "" {
		t.Errorf("signalNameFromState(normal exit) = %q, want empty", got)
	}

	cases := []struct {
		name string
		sig  syscall.Signal
		want string
	}{
		{"SIGTERM", syscall.SIGTERM, "SIGTERM"},
		{"SIGKILL", syscall.SIGKILL, "SIGKILL"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			cmd := exec.Command("sleep", "30")
			if err := cmd.Start(); err != nil {
				t.Fatalf("start sleep: %v", err)
			}
			if err := cmd.Process.Signal(tc.sig); err != nil {
				t.Fatalf("send %v: %v", tc.sig, err)
			}
			if err := cmd.Wait(); err == nil {
				t.Fatalf("expected non-zero wait status after %v", tc.sig)
			}
			if got := signalNameFromState(cmd.ProcessState); got != tc.want {
				t.Errorf("signalNameFromState = %q, want %q", got, tc.want)
			}
		})
	}
}
