package agent

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// completer_test.go — 补全功能的边界测试。
// 与 executor_test.go 一致，直接跑真实的 bash compgen，验证补全行为。

func newTestCompleter(t *testing.T, defaultDir string) *Executor {
	t.Helper()
	e := NewExecutor("/bin/bash", defaultDir, nil, nil, nil)
	if !strings.Contains(e.shell, "bash") {
		t.Fatalf("测试依赖 bash（compgen），但 shell 解析为 %q", e.shell)
	}
	return e
}

func TestComplete_CommandPosition(t *testing.T) {
	e := newTestCompleter(t, "/tmp")

	result := e.Complete(CompleteRequest{
		RequestID: "req-1",
		Line:      "ls",
		Cursor:    2,
	})

	if result.Error != "" {
		t.Fatalf("expected no error, got %q", result.Error)
	}
	if result.Prefix != "ls" {
		t.Errorf("expected prefix ls, got %q", result.Prefix)
	}
	// compgen -c 返回的候选都以 prefix 开头，且 ls 一定在 PATH 中
	found := false
	for _, c := range result.Candidates {
		if !strings.HasPrefix(c, "ls") {
			t.Errorf("candidate %q does not start with prefix %q", c, result.Prefix)
		}
		if c == "ls" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected ls in candidates, got %v", result.Candidates)
	}
}

func TestComplete_FilePath(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "abcd.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, "abcd_dir"), 0o755); err != nil {
		t.Fatal(err)
	}
	e := newTestCompleter(t, dir)

	result := e.Complete(CompleteRequest{
		RequestID: "req-2",
		Line:      "cat ./abcd",
		Cursor:    10,
	})

	if result.Error != "" {
		t.Fatalf("expected no error, got %q", result.Error)
	}
	if result.Prefix != "./abcd" {
		t.Errorf("expected prefix ./abcd, got %q", result.Prefix)
	}
	got := map[string]bool{}
	for _, c := range result.Candidates {
		got[c] = true
	}
	// compgen -f 对目录会追加 /，文件名原样返回
	if !got["./abcd.txt"] {
		t.Errorf("expected ./abcd.txt in candidates, got %v", result.Candidates)
	}
	if !got["./abcd_dir/"] {
		t.Errorf("expected ./abcd_dir/ in candidates, got %v", result.Candidates)
	}
}

func TestComplete_CdOnlyDirectories(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "xfile.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, "xdir"), 0o755); err != nil {
		t.Fatal(err)
	}
	e := newTestCompleter(t, dir)

	result := e.Complete(CompleteRequest{
		RequestID: "req-3",
		Line:      "cd ./x",
		Cursor:    6,
	})

	if result.Error != "" {
		t.Fatalf("expected no error, got %q", result.Error)
	}
	for _, c := range result.Candidates {
		if !strings.HasSuffix(c, "/") {
			t.Errorf("cd 补全只应返回目录，但候选 %q 不是目录", c)
		}
	}
}

func TestComplete_EmptyToken(t *testing.T) {
	e := newTestCompleter(t, "/tmp")

	// "ls " 之后 token 为空：不执行补全，避免弹出全量命令列表
	result := e.Complete(CompleteRequest{
		RequestID: "req-4",
		Line:      "ls ",
		Cursor:    3,
	})

	if result.Error != "" {
		t.Fatalf("expected no error, got %q", result.Error)
	}
	if len(result.Candidates) != 0 {
		t.Errorf("expected no candidates for empty token, got %v", result.Candidates)
	}
}

func TestComplete_QuotedPath(t *testing.T) {
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, "my dir"), 0o755); err != nil {
		t.Fatal(err)
	}
	e := newTestCompleter(t, dir)

	// 引号内的空格不应被当作 token 分隔符；补全应剥掉引号
	result := e.Complete(CompleteRequest{
		RequestID: "req-5",
		Line:      `cd "./my d`,
		Cursor:    10,
	})

	if result.Error != "" {
		t.Fatalf("expected no error, got %q", result.Error)
	}
	if result.Prefix != "./my d" {
		t.Errorf("expected prefix ./my d, got %q", result.Prefix)
	}
}

func TestComplete_ShellUnavailable(t *testing.T) {
	// 直接构造 Executor（绕过 NewExecutor 的 shell 降级），模拟 compgen 不存在
	e := &Executor{shell: "/nonexistent/shell", defaultDir: "/tmp"}

	result := e.Complete(CompleteRequest{
		RequestID: "req-6",
		Line:      "ls",
		Cursor:    2,
	})

	if result.Error == "" {
		t.Fatal("expected error when shell unavailable, got none")
	}
	if len(result.Candidates) != 0 {
		t.Errorf("expected no candidates on failure, got %v", result.Candidates)
	}
}

func TestComplete_DefaultDirUsedWhenCwdEmpty(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "zzz.txt"), []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}
	e := newTestCompleter(t, dir)

	// Cwd 为空时应回退到 defaultDir（agent work dir）
	result := e.Complete(CompleteRequest{
		RequestID: "req-7",
		Line:      "cat ./zz",
		Cursor:    8,
	})

	if result.Error != "" {
		t.Fatalf("expected no error, got %q", result.Error)
	}
	for _, c := range result.Candidates {
		if c == "./zzz.txt" {
			return
		}
	}
	t.Errorf("expected ./zzz.txt in candidates (from defaultDir), got %v", result.Candidates)
}
