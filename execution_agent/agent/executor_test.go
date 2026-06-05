package agent

import (
	"os"
	"syscall"
	"testing"
	"time"
)

func TestExecutorSuccess(t *testing.T) {
	var receivedResult *ExecResult
	resultCh := make(chan ExecResult, 1)

	executor := NewExecutor("/bin/sh",
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

	executor := NewExecutor("/bin/sh",
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

	executor := NewExecutor("/bin/sh",
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

	executor := NewExecutor("/bin/sh",
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

func TestExecutorEnv(t *testing.T) {
	resultCh := make(chan ExecResult, 1)
	var stdout string

	executor := NewExecutor("/bin/sh",
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
	executor := NewExecutor("/bin/sh", nil, nil, nil)

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

	executor := NewExecutor("/nonexistent/shell",
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
