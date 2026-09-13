package agent

import (
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

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
	// 原用例只调用不变量；重写为验证可观测行为：
	// 短任务必须回调 stdout 与 exit_code=0，CancelAll 必须终止长任务并回调负退出码。
	var stdoutMu sync.Mutex
	var stdout string
	results := make(chan ExecResult, 4)

	executor := NewExecutor("/bin/sh", "/tmp",
		func(cid, data string) {
			stdoutMu.Lock()
			stdout += data
			stdoutMu.Unlock()
		},
		func(cid, data string) {},
		func(result ExecResult) { results <- result },
	)

	executor.Execute(ExecCommand{CommandID: "a", Command: "sleep 30", Cwd: "/tmp"})
	executor.Execute(ExecCommand{CommandID: "b", Command: "echo done", Cwd: "/tmp"})

	resultB := waitResult(t, results, "b", 5*time.Second)
	if resultB.ExitCode != 0 {
		t.Errorf("expected b exit_code=0, got %d (err=%q)", resultB.ExitCode, resultB.Error)
	}
	stdoutMu.Lock()
	gotStdout := stdout
	stdoutMu.Unlock()
	if !strings.Contains(gotStdout, "done") {
		t.Errorf("expected stdout to contain 'done', got %q", gotStdout)
	}

	executor.CancelAll()
	resultA := waitResult(t, results, "a", 10*time.Second)
	if resultA.ExitCode >= 0 {
		t.Errorf("expected negative exit_code for cancelled command a, got %d", resultA.ExitCode)
	}
}

// waitResult 等待指定 CommandID 的结果回调，超时则 fail。
// 为什么需要按 ID 过滤：两条命令的完成顺序取决于调度，直接取第一个结果会偶发失败。
func waitResult(t *testing.T, results <-chan ExecResult, commandID string, timeout time.Duration) ExecResult {
	t.Helper()
	deadline := time.After(timeout)
	for {
		select {
		case r := <-results:
			if r.CommandID == commandID {
				return r
			}
		case <-deadline:
			t.Fatalf("timeout waiting for result of command %s", commandID)
		}
	}
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

// TestMergeEnv 合并了原 TestMergeEnv + 5 个 TestMergeEnv_* 用例，
// 用表驱动断言 key/value 与覆盖语义，而不是只断言元素个数。
func TestMergeEnv(t *testing.T) {
	tests := []struct {
		name  string
		base  []string
		extra map[string]string
		want  map[string]string // 期望有效值：同名 key 以 extra 为准
	}{
		{"empty base and extra", []string{}, nil, map[string]string{}},
		{"only base", []string{"PATH=/usr/bin", "HOME=/root"}, nil, map[string]string{"PATH": "/usr/bin", "HOME": "/root"}},
		{"add new key", []string{"PATH=/usr/bin"}, map[string]string{"KEY": "VAL"}, map[string]string{"PATH": "/usr/bin", "KEY": "VAL"}},
		{"overwrite existing key", []string{"KEY=old", "A=1"}, map[string]string{"KEY": "new"}, map[string]string{"KEY": "new", "A": "1"}},
		{"empty base with extra", []string{}, map[string]string{"NEW": "VAL"}, map[string]string{"NEW": "VAL"}},
		{"multiple extras", []string{"A=1"}, map[string]string{"B": "2", "C": "3"}, map[string]string{"A": "1", "B": "2", "C": "3"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			baseCopy := append([]string(nil), tt.base...)
			merged := mergeEnv(tt.base, tt.extra)
			if len(merged) != len(baseCopy)+len(tt.extra) {
				t.Errorf("len(merged)=%d, want %d", len(merged), len(baseCopy)+len(tt.extra))
			}
			for key, want := range tt.want {
				if got := envLastValue(merged, key); got != want {
					t.Errorf("env %s=%q, want %q (merged=%v)", key, got, want, merged)
				}
			}
			// mergeEnv 必须复制 base，不能原地修改调用方的切片
			for i := range baseCopy {
				if tt.base[i] != baseCopy[i] {
					t.Errorf("base mutated at %d: %q -> %q", i, baseCopy[i], tt.base[i])
				}
			}
		})
	}
}

// envLastValue 返回 env 中某个 key 的有效值（最后一个同名项）。
// os/exec 文档规定重复环境变量取切片中最后一个，与子进程实际读取一致；
// 因此覆盖语义按"最后一项"断言，而不是要求 mergeEnv 先做去重。
func envLastValue(env []string, key string) string {
	value := ""
	for _, item := range env {
		k, v, ok := strings.Cut(item, "=")
		if ok && k == key {
			value = v
		}
	}
	return value
}

func TestProcessCheck(t *testing.T) {
	// 原用例丢弃 collectDescendants 结果；重写为用真实子进程验证 /proc 父子解析。
	child := exec.Command("sleep", "30")
	if err := child.Start(); err != nil {
		t.Fatalf("启动子进程失败: %v", err)
	}
	childPID := child.Process.Pid
	t.Cleanup(func() {
		_ = child.Process.Kill()
		_, _ = child.Process.Wait()
	})

	desc := collectDescendants(os.Getpid())
	found := false
	for _, pid := range desc {
		if pid == childPID {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected child %d in descendants %v", childPID, desc)
	}

	if got := readPPID(childPID); got != os.Getpid() {
		t.Errorf("readPPID(%d) = %d, want %d", childPID, got, os.Getpid())
	}
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
