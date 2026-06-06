package logger

import (
	"bytes"
	"log"
	"path/filepath"
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

func TestGetLevel(t *testing.T) {
	SetLevel(3)
	if got := GetLevel(); got != LevelInfo {
		t.Errorf("GetLevel() = %v, want %v", got, LevelInfo)
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

func TestDefaultLevelIsInfo(t *testing.T) {
	SetLevel(3)
	defer SetLevel(3)

	if GetLevel() != LevelInfo {
		t.Errorf("Expected default level to be LevelInfo, got %v", GetLevel())
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
	if !strings.Contains(output, "[INFO]") {
		t.Errorf("Expected log to contain [INFO], got: %s", output)
	}
	if !strings.Contains(output, "test message 42") {
		t.Errorf("Expected log to contain 'test message 42', got: %s", output)
	}
}