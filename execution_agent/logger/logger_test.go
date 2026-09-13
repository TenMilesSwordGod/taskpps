package logger

import (
	"bytes"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestInitStderr(t *testing.T) {
	if err := Init(""); err != nil {
		t.Fatalf("Init('') failed: %v", err)
	}
	defer Close()

	if writer == nil {
		t.Fatal("writer should not be nil after Init('')")
	}
}

func TestInitFile(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "test.log")

	if err := Init(logPath); err != nil {
		t.Fatalf("Init(%q) failed: %v", logPath, err)
	}
	defer Close()

	if writer == nil {
		t.Fatal("writer should not be nil after Init(path)")
	}
	if logFile == nil {
		t.Fatal("logFile should not be nil after Init(path)")
	}
}

func TestClose(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "test.log")

	if err := Init(logPath); err != nil {
		t.Fatalf("Init failed: %v", err)
	}
	if err := Close(); err != nil {
		t.Errorf("Close() error: %v", err)
	}
	if logFile != nil {
		t.Error("logFile should be nil after Close()")
	}
}

func TestCloseNoFile(t *testing.T) {
	if err := Init(""); err != nil {
		t.Fatalf("Init('') failed: %v", err)
	}
	if err := Close(); err != nil {
		t.Errorf("Close() with no file error: %v", err)
	}
}

func TestSetLevel(t *testing.T) {
	testCases := []struct {
		name     string
		input    int
		expected LogLevel
	}{
		{name: "LevelNone/0", input: 0, expected: LevelNone},
		{name: "LevelError", input: 1, expected: LevelError},
		{name: "LevelWarn", input: 2, expected: LevelWarn},
		{name: "LevelInfo", input: 3, expected: LevelInfo},
		{name: "LevelDebug", input: 4, expected: LevelDebug},
		{name: ">=5", input: 5, expected: LevelDebug},
		{name: "negative", input: -1, expected: LevelNone},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			SetLevel(tc.input)
			if got := GetLevel(); got != tc.expected {
				t.Errorf("SetLevel(%d) = %v, want %v", tc.input, got, tc.expected)
			}
		})
	}
}

func TestSetLevelByName(t *testing.T) {
	testCases := []struct {
		name     string
		input    string
		expected LogLevel
		ok       bool
	}{
		{name: "NONE", input: "NONE", expected: LevelNone, ok: true},
		{name: "ERROR", input: "ERROR", expected: LevelError, ok: true},
		{name: "WARN", input: "WARN", expected: LevelWarn, ok: true},
		{name: "INFO", input: "INFO", expected: LevelInfo, ok: true},
		{name: "DEBUG", input: "DEBUG", expected: LevelDebug, ok: true},
		{name: "lowercase", input: "debug", expected: LevelNone, ok: false},
		{name: "unknown", input: "TRACE", expected: LevelNone, ok: false},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			SetLevel(4)
			ok := SetLevelByName(tc.input)
			if ok != tc.ok {
				t.Errorf("SetLevelByName(%q) ok = %v, want %v", tc.input, ok, tc.ok)
			}
			if ok && GetLevel() != tc.expected {
				t.Errorf("SetLevelByName(%q) = %v, want %v", tc.input, GetLevel(), tc.expected)
			}
		})
	}
}

func TestLogLevelString(t *testing.T) {
	testCases := []struct {
		level    LogLevel
		expected string
	}{
		{LevelNone, "NONE"},
		{LevelError, "ERROR"},
		{LevelWarn, "WARN"},
		{LevelInfo, "INFO"},
		{LevelDebug, "DEBUG"},
		{LogLevel(99), "LEVEL(99)"},
	}

	for _, tc := range testCases {
		t.Run(tc.expected, func(t *testing.T) {
			if got := tc.level.String(); got != tc.expected {
				t.Errorf("LogLevel(%d).String() = %q, want %q", tc.level, got, tc.expected)
			}
		})
	}
}

func TestLogLevelFiltering(t *testing.T) {
	dir := t.TempDir()
	logPath := filepath.Join(dir, "test.log")

	if err := Init(logPath); err != nil {
		t.Fatalf("Init failed: %v", err)
	}
	defer Close()

	oldLevel := GetLevel()
	defer SetLevel(int(oldLevel))

	testCases := []struct {
		name        string
		level       int
		logFunc     func(string, ...interface{})
		message     string
		expectToLog bool
		expectedTag string
	}{
		{name: "Debug at LevelNone", level: 0, logFunc: Debug, message: "debug msg", expectToLog: false, expectedTag: "DEBUG"},
		{name: "Info at LevelNone", level: 0, logFunc: Info, message: "info msg", expectToLog: false, expectedTag: "INFO"},
		{name: "Warn at LevelNone", level: 0, logFunc: Warn, message: "warn msg", expectToLog: false, expectedTag: "WARN"},
		{name: "Error at LevelNone", level: 0, logFunc: Error, message: "error msg", expectToLog: false, expectedTag: "ERROR"},
		{name: "Error at LevelError", level: 1, logFunc: Error, message: "error msg", expectToLog: true, expectedTag: "ERROR"},
		{name: "Warn at LevelError", level: 1, logFunc: Warn, message: "warn msg", expectToLog: false, expectedTag: "WARN"},
		{name: "Warn at LevelWarn", level: 2, logFunc: Warn, message: "warn msg", expectToLog: true, expectedTag: "WARN"},
		{name: "Info at LevelWarn", level: 2, logFunc: Info, message: "info msg", expectToLog: false, expectedTag: "INFO"},
		{name: "Info at LevelInfo", level: 3, logFunc: Info, message: "info msg", expectToLog: true, expectedTag: "INFO"},
		{name: "Debug at LevelInfo", level: 3, logFunc: Debug, message: "debug msg", expectToLog: false, expectedTag: "DEBUG"},
		{name: "Debug at LevelDebug", level: 4, logFunc: Debug, message: "debug msg", expectToLog: true, expectedTag: "DEBUG"},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			SetLevel(tc.level)

			var buf bytes.Buffer
			mu.Lock()
			writer = log.New(&buf, "", 0)
			mu.Unlock()

			tc.logFunc(tc.message)

			output := buf.String()

			if tc.expectToLog {
				if len(output) == 0 {
					t.Errorf("Expected log output, got nothing")
				}
				if !strings.Contains(output, tc.expectedTag) {
					t.Errorf("Expected log to contain '%s', got: %s", tc.expectedTag, output)
				}
				if !strings.Contains(output, tc.message) {
					t.Errorf("Expected log to contain '%s', got: %s", tc.message, output)
				}
			} else {
				if len(output) != 0 {
					t.Errorf("Expected no log output, got: %s", output)
				}
			}
		})
	}
}

// TestDefaultLevelIsInfo 验证包初始化时 level 的默认值。
//
// 为什么用子进程：同包其他用例（TestSetLevel/TestSetLevelByName/TestLogLevelFiltering）
// 会修改包级 level，顺序执行时无法在测试进程内观察真正的 init 默认值；
// 原实现先 SetLevel(3) 再断言 ==3，属自证循环。子进程只运行本用例，
// 不经过任何 Set*，读到的就是初始化值。
func TestDefaultLevelIsInfo(t *testing.T) {
	if os.Getenv("TASKPPS_LOGGER_DEFAULT_LEVEL_CHILD") == "1" {
		if got := GetLevel(); got != LevelInfo {
			t.Fatalf("default level = %v, want LevelInfo", got)
		}
		fmt.Println("default-level-check-ok")
		return
	}

	cmd := exec.Command(os.Args[0], "-test.run=^TestDefaultLevelIsInfo$", "-test.v")
	cmd.Env = append(os.Environ(), "TASKPPS_LOGGER_DEFAULT_LEVEL_CHILD=1")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("子进程默认级别校验失败: %v\n%s", err, out)
	}
	if !strings.Contains(string(out), "default-level-check-ok") {
		t.Fatalf("子进程未执行默认级别分支，输出:\n%s", out)
	}
}

func TestLogFormat(t *testing.T) {
	var buf bytes.Buffer
	mu.Lock()
	writer = log.New(&buf, "", 0)
	mu.Unlock()

	SetLevel(4)
	Info("test message %d", 42)

	output := buf.String()
	// 断言完整格式 [时间戳] [级别] 消息，而不是只查 [INFO] 子串：
	// 时间戳缺失、级别位置漂移、换行/前缀丢失都必须能被捕获。
	pattern := `^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)\] \[INFO\] test message 42\n$`
	matched, err := regexp.MatchString(pattern, output)
	if err != nil {
		t.Fatalf("invalid pattern: %v", err)
	}
	if !matched {
		t.Errorf("log line %q does not match full format %s", output, pattern)
	}
}
