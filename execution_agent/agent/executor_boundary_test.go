package agent

import (
	"testing"
)

func TestNewExecutor_DefaultShell(t *testing.T) {
	exec := NewExecutor("", "/tmp", nil, nil, nil)
	if exec.shell != "/bin/bash" {
		t.Errorf("expected /bin/bash, got %s", exec.shell)
	}
	if exec.defaultDir != "/tmp" {
		t.Errorf("expected /tmp, got %s", exec.defaultDir)
	}
}

func TestNewExecutor_CustomShell(t *testing.T) {
	exec := NewExecutor("/bin/sh", "/home", nil, nil, nil)
	if exec.shell != "/bin/sh" {
		t.Errorf("expected /bin/sh, got %s", exec.shell)
	}
}

func TestNewExecutor_NilCallbacks(t *testing.T) {
	exec := NewExecutor("/bin/bash", "/tmp", nil, nil, nil)
	if exec.onStdout != nil {
		t.Errorf("expected nil onStdout")
	}
	if exec.onStderr != nil {
		t.Errorf("expected nil onStderr")
	}
	if exec.onResult != nil {
		t.Errorf("expected nil onResult")
	}
}

func TestNewExecutor_WithCallbacks(t *testing.T) {
	stdoutCalled := false
	stderrCalled := false
	resultCalled := false

	onStdout := func(commandID, data string) {
		stdoutCalled = true
	}
	onStderr := func(commandID, data string) {
		stderrCalled = true
	}
	onResult := func(result ExecResult) {
		resultCalled = true
	}

	exec := NewExecutor("/bin/bash", "/tmp", onStdout, onStderr, onResult)
	if exec.onStdout == nil {
		t.Errorf("expected non-nil onStdout")
	}
	exec.onStdout("test", "data")
	if !stdoutCalled {
		t.Errorf("expected onStdout to be called")
	}

	exec.onStderr("test", "data")
	if !stderrCalled {
		t.Errorf("expected onStderr to be called")
	}

	exec.onResult(ExecResult{})
	if !resultCalled {
		t.Errorf("expected onResult to be called")
	}
}

func TestMergeEnv_Empty(t *testing.T) {
	result := mergeEnv([]string{}, nil)
	if len(result) != 0 {
		t.Errorf("expected empty result, got %d items", len(result))
	}
}

func TestMergeEnv_AddNew(t *testing.T) {
	result := mergeEnv([]string{"PATH=/usr/bin"}, map[string]string{"KEY": "VAL"})
	if len(result) != 2 {
		t.Errorf("expected 2 items, got %d", len(result))
	}
	found := false
	for _, s := range result {
		if s == "KEY=VAL" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected KEY=VAL in result")
	}
}

func TestMergeEnv_Overwrite(t *testing.T) {
	result := mergeEnv([]string{"KEY=old"}, map[string]string{"KEY": "new"})
	found := false
	for _, s := range result {
		if s == "KEY=new" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("expected KEY=new in result")
	}
}

func TestMergeEnv_NilExtra(t *testing.T) {
	base := []string{"A=B", "C=D"}
	result := mergeEnv(base, nil)
	if len(result) != 2 {
		t.Errorf("expected 2 items, got %d", len(result))
	}
}

func TestMergeEnv_EmptyBase(t *testing.T) {
	result := mergeEnv([]string{}, map[string]string{"NEW": "VAL"})
	if len(result) != 1 {
		t.Errorf("expected 1 item, got %d", len(result))
	}
	if result[0] != "NEW=VAL" {
		t.Errorf("expected NEW=VAL, got %s", result[0])
	}
}

func TestMergeEnv_MultipleKeys(t *testing.T) {
	result := mergeEnv([]string{"A=1"}, map[string]string{"B": "2", "C": "3"})
	if len(result) != 3 {
		t.Errorf("expected 3 items, got %d", len(result))
	}
}

func TestExecutor_CancelNonExistent(t *testing.T) {
	exec := NewExecutor("/bin/bash", "/tmp", nil, nil, nil)
	exec.Cancel("nonexistent")
}

func TestExecutor_CancelAllEmpty(t *testing.T) {
	exec := NewExecutor("/bin/bash", "/tmp", nil, nil, nil)
	exec.CancelAll()
}

func TestExecutor_SendResultNilCallback(t *testing.T) {
	exec := NewExecutor("/bin/bash", "/tmp", nil, nil, nil)
	exec.sendResult(ExecResult{CommandID: "test", ExitCode: 0})
}

func TestExecutor_SendResultWithCallback(t *testing.T) {
	var received ExecResult
	onResult := func(result ExecResult) {
		received = result
	}
	exec := NewExecutor("/bin/bash", "/tmp", nil, nil, onResult)
	exec.sendResult(ExecResult{CommandID: "test", ExitCode: 42, DurationMs: 100})

	if received.CommandID != "test" {
		t.Errorf("expected test, got %s", received.CommandID)
	}
	if received.ExitCode != 42 {
		t.Errorf("expected 42, got %d", received.ExitCode)
	}
	if received.DurationMs != 100 {
		t.Errorf("expected 100, got %d", received.DurationMs)
	}
}