package agent

import (
	"os"
	"os/exec"
	"path/filepath"
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

// createUnexecutableScript 创建一个有执行权限但无法实际运行的脚本。
// 模拟精简环境中 /bin/bash 存在但动态链接器缺失的场景（issue #171）。
func createUnexecutableScript(t *testing.T, dir string) string {
	t.Helper()
	path := filepath.Join(dir, "fake-shell")
	// 使用不存在的解释器，文件有执行权限但 fork/exec 会失败
	err := os.WriteFile(path, []byte("#!/nonexistent/interpreter\necho hello"), 0755)
	if err != nil {
		t.Fatalf("创建测试脚本失败: %v", err)
	}
	return path
}

func TestIsExecutable_EmptyPath(t *testing.T) {
	if isExecutable("") {
		t.Error("空路径应返回 false")
	}
}

func TestIsExecutable_NonexistentPath(t *testing.T) {
	if isExecutable("/nonexistent/path/to/shell") {
		t.Error("不存在的路径应返回 false")
	}
}

func TestIsExecutable_ValidShell(t *testing.T) {
	// /bin/sh 在大多数 Linux 系统上存在且可执行
	shPath, err := exec.LookPath("sh")
	if err != nil {
		t.Skip("系统中找不到 sh，跳过测试")
	}
	if !isExecutable(shPath) {
		t.Errorf("有效的 shell %q 应返回 true", shPath)
	}
}

// TestIsExecutable_FileExistsButCannotExecute 验证 issue #171 的核心场景：
// 文件存在且有执行权限，但由于动态链接器缺失等原因无法实际执行。
func TestIsExecutable_FileExistsButCannotExecute(t *testing.T) {
	dir := t.TempDir()
	fakePath := createUnexecutableScript(t, dir)

	// exec.LookPath 应能找到该文件（存在且有执行权限）
	resolved, err := exec.LookPath(fakePath)
	if err != nil {
		t.Fatalf("LookPath 应能找到文件: %v", err)
	}
	if resolved == "" {
		t.Fatal("LookPath 应返回非空路径")
	}

	// 但 isExecutable 应返回 false，因为实际执行会失败
	if isExecutable(fakePath) {
		t.Error("无法实际执行的文件应返回 false（issue #171 修复验证）")
	}
}

// TestResolveShell_SkipsUnexecutableShell 验证 resolveShell 会跳过无法执行的 shell，
// 即使它在 fallback 列表中排在前面。
func TestResolveShell_SkipsUnexecutableShell(t *testing.T) {
	dir := t.TempDir()
	fakePath := createUnexecutableScript(t, dir)

	// 保存并替换 fallback 列表，将 fake shell 放在最前面
	original := shellFallbacks
	shellFallbacks = append([]string{fakePath}, original...)
	defer func() { shellFallbacks = original }()

	// 使用一个不存在的 shell 触发 fallback
	result := resolveShell("/nonexistent/configured/shell")

	// 结果不应该是 fake shell
	if result == fakePath {
		t.Error("resolveShell 不应选择无法执行的 shell")
	}

	// 结果应该是 fallback 列表中真正可用的 shell
	if result == "/nonexistent/configured/shell" {
		t.Error("resolveShell 不应回退到原始不存在的 shell")
	}

	// 验证结果是列表中真正可执行的
	if !isExecutable(result) {
		t.Errorf("resolveShell 选择了不可执行的 shell: %q", result)
	}
}

// TestResolveShell_AllFallbacksUnexecutable 验证所有 fallback 都无法执行时，
// 保留原配置让其失败以便定位。
func TestResolveShell_AllFallbacksUnexecutable(t *testing.T) {
	dir := t.TempDir()
	fake1 := createUnexecutableScript(t, dir)
	fake2 := filepath.Join(dir, "fake-shell2")
	os.WriteFile(fake2, []byte("#!/also/nonexistent\necho hello"), 0755)

	original := shellFallbacks
	shellFallbacks = []string{fake1, fake2}
	defer func() { shellFallbacks = original }()

	configured := "/missing/configured/shell"
	result := resolveShell(configured)

	// 所有 fallback 都不可用时，应保留原配置
	if result != configured {
		t.Errorf("所有 fallback 不可用时应保留原配置 %q, got %q", configured, result)
	}
}

// TestNewExecutor_FallbackFromBrokenShell 验证端到端场景：
// 配置的 shell 无法执行时，executor 自动降级到可用 shell。
func TestNewExecutor_FallbackFromBrokenShell(t *testing.T) {
	dir := t.TempDir()
	fakePath := createUnexecutableScript(t, dir)

	original := shellFallbacks
	shellFallbacks = []string{"/bin/sh"} // 只保留一个确定可用的
	defer func() { shellFallbacks = original }()

	executor := NewExecutor(fakePath, dir, nil, nil, nil)

	// executor 应该使用 /bin/sh 而非 fake shell
	if executor.shell == fakePath {
		t.Error("executor 不应使用无法执行的 shell")
	}
	if executor.shell != "/bin/sh" {
		t.Errorf("executor 应降级到 /bin/sh, got %q", executor.shell)
	}
}