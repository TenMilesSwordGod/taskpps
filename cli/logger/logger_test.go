package logger

import (
	"bytes"
	"io"
	"os"
	"testing"
)

func TestSetLevel(t *testing.T) {
	testCases := []struct {
		name     string
		input    int
		expected LogLevel
	}{
		{
			name:     "LevelNone by default/0",
			input:    0,
			expected: LevelNone,
		},
		{
			name:     "LevelError",
			input:    1,
			expected: LevelError,
		},
		{
			name:     "LevelWarn",
			input:    2,
			expected: LevelWarn,
		},
		{
			name:     "LevelInfo",
			input:    3,
			expected: LevelInfo,
		},
		{
			name:     "LevelDebug",
			input:    4,
			expected: LevelDebug,
		},
		{
			name:     "LevelDebug (>=4)",
			input:    5,
			expected: LevelDebug,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			SetLevel(tc.input)
			if currentLevel != tc.expected {
				t.Errorf("SetLevel(%d) = %v, want %v", tc.input, currentLevel, tc.expected)
			}
		})
	}
}

func TestLoggingAtDifferentLevels(t *testing.T) {
	// Save original state
	oldLevel := currentLevel
	oldOutput := debugLogger.Writer()
	defer func() {
		currentLevel = oldLevel
		SetOutput(oldOutput)
	}()

	var buf bytes.Buffer
	SetOutput(&buf)

	testCases := []struct {
		name           string
		level          int
		logFunc        func(string, ...interface{})
		message        string
		expectToLog    bool
		expectedPrefix string
	}{
		{
			name:           "Debug at LevelNone - not logged",
			level:          0,
			logFunc:        Debug,
			message:        "test debug",
			expectToLog:    false,
			expectedPrefix: "[DEBUG]",
		},
		{
			name:           "Info at LevelNone - not logged",
			level:          0,
			logFunc:        Info,
			message:        "test info",
			expectToLog:    false,
			expectedPrefix: "[INFO]",
		},
		{
			name:           "Warn at LevelNone - not logged",
			level:          0,
			logFunc:        Warn,
			message:        "test warn",
			expectToLog:    false,
			expectedPrefix: "[WARN]",
		},
		{
			name:           "Error at LevelNone - not logged",
			level:          0,
			logFunc:        Error,
			message:        "test error",
			expectToLog:    false,
			expectedPrefix: "[ERROR]",
		},
		{
			name:           "Error at LevelError - logged",
			level:          1,
			logFunc:        Error,
			message:        "test error 1",
			expectToLog:    true,
			expectedPrefix: "[ERROR]",
		},
		{
			name:           "Warn at LevelError - not logged",
			level:          1,
			logFunc:        Warn,
			message:        "test warn 1",
			expectToLog:    false,
			expectedPrefix: "[WARN]",
		},
		{
			name:           "Warn at LevelWarn - logged",
			level:          2,
			logFunc:        Warn,
			message:        "test warn 2",
			expectToLog:    true,
			expectedPrefix: "[WARN]",
		},
		{
			name:           "Info at LevelWarn - not logged",
			level:          2,
			logFunc:        Info,
			message:        "test info 2",
			expectToLog:    false,
			expectedPrefix: "[INFO]",
		},
		{
			name:           "Info at LevelInfo - logged",
			level:          3,
			logFunc:        Info,
			message:        "test info 3",
			expectToLog:    true,
			expectedPrefix: "[INFO]",
		},
		{
			name:           "Debug at LevelInfo - not logged",
			level:          3,
			logFunc:        Debug,
			message:        "test debug 3",
			expectToLog:    false,
			expectedPrefix: "[DEBUG]",
		},
		{
			name:           "Debug at LevelDebug - logged",
			level:          4,
			logFunc:        Debug,
			message:        "test debug 4",
			expectToLog:    true,
			expectedPrefix: "[DEBUG]",
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			buf.Reset()
			SetLevel(tc.level)
			tc.logFunc(tc.message)
			output := buf.String()

			if tc.expectToLog {
				if len(output) == 0 {
					t.Errorf("Expected log output, got nothing")
				}
				if !bytes.Contains([]byte(output), []byte(tc.expectedPrefix)) {
					t.Errorf("Expected log to contain '%s', got: %s", tc.expectedPrefix, output)
				}
			} else {
				if len(output) != 0 {
					t.Errorf("Expected no log output, got: %s", output)
				}
			}
		})
	}
}

func TestSetOutput(t *testing.T) {
	oldLevel := currentLevel
	oldOutput := debugLogger.Writer()
	defer func() {
		currentLevel = oldLevel
		SetOutput(oldOutput)
	}()

	var buf1 bytes.Buffer
	SetOutput(&buf1)
	SetLevel(4) // LevelDebug
	Debug("test to buf1")
	if !bytes.Contains(buf1.Bytes(), []byte("test to buf1")) {
		t.Error("Expected log to buf1, but not found")
	}

	var buf2 bytes.Buffer
	SetOutput(&buf2)
	Debug("test to buf2")
	if !bytes.Contains(buf2.Bytes(), []byte("test to buf2")) {
		t.Error("Expected log to buf2, but not found")
	}
	// Check buf1 doesn't have buf2's log
	if bytes.Contains(buf1.Bytes(), []byte("test to buf2")) {
		t.Error("buf1 should not have buf2's log")
	}
}

func TestEnableVerboseOutput(t *testing.T) {
	oldLevel := currentLevel
	oldOutput := debugLogger.Writer()
	defer func() {
		currentLevel = oldLevel
		SetOutput(oldOutput)
	}()

	// Set output to io.Discard first
	SetOutput(io.Discard)
	var buf bytes.Buffer

	// Now enable verbose output
	EnableVerboseOutput()

	// Check that the output is os.Stderr
	if debugLogger.Writer() != os.Stderr {
		t.Errorf("Expected writer to be os.Stderr after EnableVerboseOutput")
	}
	if infoLogger.Writer() != os.Stderr {
		t.Errorf("Expected info writer to be os.Stderr after EnableVerboseOutput")
	}
	if warnLogger.Writer() != os.Stderr {
		t.Errorf("Expected warn writer to be os.Stderr after EnableVerboseOutput")
	}
	if errorLogger.Writer() != os.Stderr {
		t.Errorf("Expected error writer to be os.Stderr after EnableVerboseOutput")
	}

	// Now test it actually logs
	SetLevel(4)
	// Replace output with buf temporarily
	SetOutput(&buf)
	Debug("test enable verbose")
	if !bytes.Contains(buf.Bytes(), []byte("test enable verbose")) {
		t.Error("Expected log after EnableVerboseOutput, but not found")
	}
}
