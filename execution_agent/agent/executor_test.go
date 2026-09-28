package agent

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

// TestExecutorPerRequestShell 验证命令级 shell 覆盖 agent 启动时的默认 shell。
// 用脚本伪造成 shell：命中标记说明 req.Shell 确实被用作解释器。
func TestExecutorPerRequestShell(t *testing.T) {
	dir := t.TempDir()
	fakeShell := filepath.Join(dir, "myshell")
	script := "#!/bin/sh\necho REQUEST_SHELL_MARKER\nexec /bin/sh \"$@\"\n"
	if err := os.WriteFile(fakeShell, []byte(script), 0o755); err != nil {
		t.Fatalf("write fake shell: %v", err)
	}

	var out strings.Builder
	resultCh := make(chan ExecResult, 1)
	executor := NewExecutor("/bin/sh", dir,
		func(cid, data string) { out.WriteString(data) },
		func(cid, data string) {},
		func(result ExecResult) { resultCh <- result },
	)

	executor.Execute(ExecCommand{
		CommandID: "shell-001",
		Command:   "echo per_request_done",
		Cwd:       dir,
		Shell:     fakeShell,
	})

	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if result.ExitCode != 0 {
		t.Errorf("expected exit_code=0, got %d", result.ExitCode)
	}
	if !strings.Contains(out.String(), "REQUEST_SHELL_MARKER") {
		t.Errorf("per-request shell not used, output=%q", out.String())
	}
	if !strings.Contains(out.String(), "per_request_done") {
		t.Errorf("command not executed, output=%q", out.String())
	}
}

// TestExecutorPerRequestShellFailsWhenMissing 验证请求里的 shell 不存在时必须
// 直接失败并把错误返回给调用方，而不是悄悄降级到 bash/dash/sh。
//
// 设计决策：启动配置的 shell 缺失走 fallback（issue #56，保证兼容老环境），
// 但命令级 shell 是用户在网页上显式配置的——静默换解释器会让用户看到
// zsh 配置却在 bash 里跑，只有 agent 端日志能发现，属于掩盖配置错误。
func TestExecutorPerRequestShellFailsWhenMissing(t *testing.T) {
	dir := t.TempDir()
	var out strings.Builder
	resultCh := make(chan ExecResult, 1)
	executor := NewExecutor("/bin/sh", dir,
		func(cid, data string) { out.WriteString(data) },
		func(cid, data string) {},
		func(result ExecResult) { resultCh <- result },
	)

	executor.Execute(ExecCommand{
		CommandID: "shell-002",
		Command:   "echo should_not_run",
		Cwd:       dir,
		Shell:     "/nonexistent/shell-xyz",
	})

	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if result.ExitCode == 0 {
		t.Errorf("expected failure for missing per-request shell, got exit_code=0 output=%q", out.String())
	}
	if result.Error == "" {
		t.Errorf("expected error message for missing shell, got empty")
	}
	if strings.Contains(out.String(), "should_not_run") {
		t.Errorf("command must not run under a fallback shell, output=%q", out.String())
	}
}

func TestExecutorSuccess(t *testing.T) {
	var receivedResult *ExecResult
	resultCh := make(chan ExecResult, 1)

	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) {
			r := result
			receivedResult = &r
			resultCh <- result
		},
	)

	executor.Execute(ExecCommand{
		CommandID: "test-001",
		Command:   "echo hello && exit 0",
		Cwd:       "/tmp",
	})

	select {
	case <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if receivedResult == nil {
		t.Fatal("no result received")
	}
	if receivedResult.ExitCode != 0 {
		t.Errorf("expected exit_code=0, got %d", receivedResult.ExitCode)
	}
}

func TestExecutorFailure(t *testing.T) {
	resultCh := make(chan ExecResult, 1)

	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) {
			resultCh <- result
		},
	)

	executor.Execute(ExecCommand{
		CommandID: "test-002",
		Command:   "exit 42",
		Cwd:       "/tmp",
	})

	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if result.ExitCode != 42 {
		t.Errorf("expected exit_code=42, got %d", result.ExitCode)
	}
}

func TestExecutorTimeout(t *testing.T) {
	resultCh := make(chan ExecResult, 1)

	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) {
			resultCh <- result
		},
	)

	executor.Execute(ExecCommand{
		CommandID: "test-003",
		Command:   "sleep 10",
		Cwd:       "/tmp",
		Timeout:   1,
	})

	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if result.ExitCode >= 0 {
		t.Errorf("expected negative exit_code (signal), got %d", result.ExitCode)
	}
	if result.SignalName != "SIGKILL" {
		t.Errorf("expected SIGKILL, got %s", result.SignalName)
	}
}

func TestExecutorCancel(t *testing.T) {
	resultCh := make(chan ExecResult, 1)

	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) {
			resultCh <- result
		},
	)

	executor.Execute(ExecCommand{
		CommandID: "test-004",
		Command:   "sleep 30",
		Cwd:       "/tmp",
	})

	time.Sleep(200 * time.Millisecond)
	executor.Cancel("test-004")

	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(10 * time.Second):
		t.Fatal("timeout waiting for cancel result")
	}

	if result.ExitCode >= 0 {
		t.Errorf("expected negative exit_code (signal), got %d", result.ExitCode)
	}
}

// TestExecutorCancelKillsChildProcess is a regression test for the bug
// where Cancel() killed the bash parent but left the command's child
// process (e.g. `sleep 30`) running as an orphan. The root cause was
// that the second Wait() in Cancel() returned immediately and skipped
// the SIGKILL fallback, plus the parent-only signal left bash's child
// to survive. The fix uses the process group signal so the whole
// subtree is killed, and waits on an Exited channel that the wait
// goroutine closes after Wait() returns.
func TestExecutorCancelKillsChildProcess(t *testing.T) {
	pidFile := t.TempDir() + "/child.pid"
	_ = os.Remove(pidFile)

	resultCh := make(chan ExecResult, 1)
	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) {
			resultCh <- result
		},
	)

	// `sh -c "sleep 30 & echo $! > pidfile; wait"`: bash spawns sleep as
	// a child, writes the sleep PID to pidfile, then waits. Cancelling
	// must kill the sleep child too — not only bash.
	executor.Execute(ExecCommand{
		CommandID: "test-cancel-child",
		Command:   "sleep 30 & echo $! > " + pidFile + "; wait",
		Cwd:       "/tmp",
	})

	// Wait for the child PID to be written.
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		if data, err := os.ReadFile(pidFile); err == nil && len(data) > 0 {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	pidData, err := os.ReadFile(pidFile)
	if err != nil || len(pidData) == 0 {
		t.Fatalf("child PID file was not written: %v", err)
	}
	childPID, err := strconv.Atoi(strings.TrimSpace(string(pidData)))
	if err != nil {
		t.Fatalf("invalid child PID %q: %v", string(pidData), err)
	}

	executor.Cancel("test-cancel-child")

	select {
	case <-resultCh:
	case <-time.After(10 * time.Second):
		t.Fatal("timeout waiting for cancel result")
	}

	// Give the kernel a moment to deliver SIGKILL and reap the child.
	time.Sleep(200 * time.Millisecond)

	if err := syscall.Kill(childPID, 0); err == nil {
		t.Errorf("child process %d is still running after cancel (orphaned)", childPID)
	} else if err != syscall.ESRCH {
		// ESRCH = "No such process" = good. Anything else is suspicious.
		t.Errorf("unexpected error checking child %d: %v", childPID, err)
	}
}

func TestExecutorEnv(t *testing.T) {
	resultCh := make(chan ExecResult, 1)
	var stdout string

	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {
			stdout += data
		},
		func(cid, data string) {},
		func(result ExecResult) {
			resultCh <- result
		},
	)

	executor.Execute(ExecCommand{
		CommandID: "test-005",
		Command:   "echo $TEST_VAR",
		Env:       map[string]string{"TEST_VAR": "hello-world"},
		Cwd:       "/tmp",
	})

	select {
	case <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if len(stdout) == 0 || !contains(stdout, "hello-world") {
		t.Errorf("expected stdout to contain hello-world, got: %s", stdout)
	}
}

func TestExecutorCommands(t *testing.T) {
	executor := NewExecutor("/bin/sh", "/tmp", nil, nil, nil)

	executor.Execute(ExecCommand{CommandID: "a", Command: "sleep 10"})
	executor.Execute(ExecCommand{CommandID: "b", Command: "echo done"})

	time.Sleep(100 * time.Millisecond)

	executor.CancelAll()
}

func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestExecutorStartError(t *testing.T) {
	resultCh := make(chan ExecResult, 1)

	// 暂时把所有 fallback 都标记为不可用，确保原始行为得到验证
	originalFallbacks := shellFallbacks
	shellFallbacks = []string{}
	defer func() { shellFallbacks = originalFallbacks }()

	executor := NewExecutor("/nonexistent/shell", "",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) {
			resultCh <- result
		},
	)

	executor.Execute(ExecCommand{
		CommandID: "test-006",
		Command:   "echo hello",
		Cwd:       "/tmp",
	})

	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}

	if result.ExitCode == 0 {
		t.Errorf("expected non-zero exit_code for nonexistent shell")
	}
}

func TestExecutorShellFallback(t *testing.T) {
	// 验证配置的 shell 不存在时，能自动降级到 fallback 列表里的可用 shell
	resultCh := make(chan ExecResult, 1)
	executor := NewExecutor("/this/shell/does/not/exist", "/tmp",
		func(cid, data string) {},
		func(cid, data string) {},
		func(result ExecResult) { resultCh <- result },
	)
	executor.Execute(ExecCommand{
		CommandID: "test-fallback",
		Command:   "echo fallback-ok",
	})
	var result ExecResult
	select {
	case result = <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}
	if result.ExitCode != 0 {
		t.Errorf("expected fallback to succeed, got exit=%d err=%q", result.ExitCode, result.Error)
	}
}

func TestExecutorCwdPassed(t *testing.T) {
	// Issue #56: 验证 Cwd 参数正确传递到命令执行环境
	tmpDir := t.TempDir()
	resultCh := make(chan ExecResult, 1)
	var stdout string
	executor := NewExecutor("/bin/sh", "/nonexistent",
		func(cid, data string) { stdout += data },
		func(cid, data string) {},
		func(result ExecResult) { resultCh <- result },
	)
	executor.Execute(ExecCommand{
		CommandID: "test-cwd",
		Command:   "pwd",
		Cwd:       tmpDir,
	})
	select {
	case <-resultCh:
	case <-time.After(5 * time.Second):
		t.Fatal("timeout waiting for result")
	}
	if !strings.Contains(stdout, tmpDir) {
		t.Errorf("expected CWD %q in stdout, got %q", tmpDir, stdout)
	}
}

func TestResolveShell(t *testing.T) {
	t.Run("空字符串返回空字符串（让 NewExecutor 走默认值）", func(t *testing.T) {
		if got := resolveShell(""); got != "" {
			t.Errorf("expected empty, got %q", got)
		}
	})
	t.Run("已存在的 shell 保持原样", func(t *testing.T) {
		if got := resolveShell("/bin/sh"); got != "/bin/sh" {
			t.Errorf("expected /bin/sh, got %q", got)
		}
	})
	t.Run("不存在的 shell 走 fallback", func(t *testing.T) {
		got := resolveShell("/no/such/shell")
		if got == "/no/such/shell" {
			// 极端环境下所有 fallback 都不存在时，会保留原值
			t.Logf("所有 fallback 都不存在，保留原值 %q（环境受限）", got)
			return
		}
		// 应当落到某个 fallback shell
		found := false
		for _, f := range shellFallbacks {
			if got == f {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("fallback %q 不在 shellFallbacks 列表中", got)
		}
	})
}

func TestSignalToString(t *testing.T) {
	tests := []struct {
		sig      syscall.Signal
		expected string
	}{
		{syscall.SIGKILL, "SIGKILL"},
		{syscall.SIGTERM, "SIGTERM"},
		{syscall.SIGINT, "SIGINT"},
		{syscall.SIGHUP, "SIGHUP"},
		{syscall.SIGSEGV, "SIGSEGV"},
		{syscall.Signal(99), "signal 99"},
	}

	for _, tt := range tests {
		got := signalToString(tt.sig)
		if got != tt.expected {
			t.Errorf("signalToString(%v) = %s, want %s", tt.sig, got, tt.expected)
		}
	}
}

func TestMergeEnv(t *testing.T) {
	merged := mergeEnv([]string{"A=1", "B=2"}, map[string]string{"C": "3"})
	if len(merged) != 3 {
		t.Errorf("expected 3 env vars, got %d", len(merged))
	}
}

func TestProcessCheck(t *testing.T) {
	pid := os.Getpid()
	desc := collectDescendants(pid)
	_ = desc
}

func TestIsDigit(t *testing.T) {
	if !isDigit("12345") {
		t.Error("expected true")
	}
	if isDigit("abc") {
		t.Error("expected false")
	}
	if isDigit("") {
		t.Error("expected false")
	}
}

func TestReadPPID(t *testing.T) {
	ppid := readPPID(os.Getpid())
	if ppid == 0 {
		t.Error("expected non-zero PPID")
	}
}
