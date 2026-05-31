package tui

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

var (
	recorder     *DebugRecorder
	recorderOnce sync.Once
)

// DebugRecorder captures TUI render output for debugging purposes.
// When verbose level >= 4 (-vvvv), it records every frame rendered by the TUI
// to a timestamped file in the issues directory.
type DebugRecorder struct {
	enabled bool
	file    *os.File
	mu      sync.Mutex
}

// GetDebugRecorder returns the singleton debug recorder instance.
func GetDebugRecorder() *DebugRecorder {
	recorderOnce.Do(func() {
		recorder = &DebugRecorder{}
	})
	return recorder
}

// Start begins recording TUI output to a file.
// The file is created in docs/issues/ with a timestamped name.
func (r *DebugRecorder) Start(command string, term string, tty string, columns int, lines int) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.enabled {
		return nil
	}

	// Find the docs/issues directory relative to current working directory
	issuesDir := filepath.Join("docs", "issues")
	if err := os.MkdirAll(issuesDir, 0755); err != nil {
		return fmt.Errorf("failed to create issues directory: %w", err)
	}

	timestamp := time.Now().Format("2006-01-02_15-04-05")
	filename := filepath.Join(issuesDir, fmt.Sprintf("debug_%s.txt", timestamp))

	file, err := os.Create(filename)
	if err != nil {
		return fmt.Errorf("failed to create debug file: %w", err)
	}

	r.file = file
	r.enabled = true

	// Write header with session info
	r.writeHeader(command, term, tty, columns, lines)

	return nil
}

// Stop stops recording and closes the file.
func (r *DebugRecorder) Stop(exitCode int) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if !r.enabled || r.file == nil {
		return
	}

	r.writeFooter(exitCode)
	r.file.Close()
	r.enabled = false
}

// RecordFrame writes a single TUI frame to the debug log.
func (r *DebugRecorder) RecordFrame(frame string) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if !r.enabled || r.file == nil {
		return
	}

	// Write timestamp and frame content
	timestamp := time.Now().Format("2006-01-02 15:04:05.000")
	fmt.Fprintf(r.file, "--- FRAME %s ---\n", timestamp)
	fmt.Fprint(r.file, frame)
	if len(frame) > 0 && frame[len(frame)-1] != '\n' {
		fmt.Fprintln(r.file)
	}
	fmt.Fprintln(r.file, "--- END FRAME ---")
}

// RecordEvent writes a non-frame event (key press, message, etc.) to the debug log.
func (r *DebugRecorder) RecordEvent(eventType string, details string) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if !r.enabled || r.file == nil {
		return
	}

	timestamp := time.Now().Format("2006-01-02 15:04:05.000")
	fmt.Fprintf(r.file, "--- EVENT %s %s ---\n", timestamp, eventType)
	fmt.Fprintln(r.file, details)
	fmt.Fprintln(r.file, "--- END EVENT ---")
}

// IsEnabled returns whether recording is currently active.
func (r *DebugRecorder) IsEnabled() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.enabled
}

func (r *DebugRecorder) writeHeader(command, term, tty string, columns, lines int) {
	if r.file == nil {
		return
	}
	tz := time.Now().Format("-07:00")
	fmt.Fprintf(r.file, "Session started %s%s [COMMAND=%q TERM=%q TTY=%q COLUMNS=%d LINES=%d]\n",
		time.Now().Format("2006-01-02 15:04:05"), tz, command, term, tty, columns, lines)
	fmt.Fprintln(r.file, strings.Repeat("=", 80))
}

func (r *DebugRecorder) writeFooter(exitCode int) {
	if r.file == nil {
		return
	}
	fmt.Fprintln(r.file, strings.Repeat("=", 80))
	fmt.Fprintf(r.file, "Session ended %s [COMMAND_EXIT_CODE=%d]\n",
		time.Now().Format("2006-01-02 15:04:05"), exitCode)
}

// EnableDebugRecorder initializes and enables the debug recorder.
// This should be called when -vvvv flag is detected.
func EnableDebugRecorder(command string, term string, tty string, columns int, lines int) error {
	return GetDebugRecorder().Start(command, term, tty, columns, lines)
}

// DisableDebugRecorder stops the debug recorder.
func DisableDebugRecorder(exitCode int) {
	GetDebugRecorder().Stop(exitCode)
}
