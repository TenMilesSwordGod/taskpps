package tui

import (
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestDebugRecorderSingleton(t *testing.T) {
	r1 := GetDebugRecorder()
	r2 := GetDebugRecorder()
	if r1 != r2 {
		t.Error("GetDebugRecorder should return the same instance")
	}
}

func TestDebugRecorderStartStop(t *testing.T) {
	// Clean up any existing recorder state
	recorder = nil
	recorderOnce = sync.Once{}

	r := GetDebugRecorder()

	err := r.Start("test-cmd", "xterm", "/dev/pts/1", 80, 24)
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	if !r.IsEnabled() {
		t.Error("recorder should be enabled after Start")
	}

	r.Stop(0)

	if r.IsEnabled() {
		t.Error("recorder should be disabled after Stop")
	}
}

func TestDebugRecorderRecordFrame(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	r := GetDebugRecorder()

	err := r.Start("watch", "xterm-256color", "/dev/pts/2", 100, 30)
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}
	defer r.Stop(0)

	r.RecordFrame("test frame content")

	// Recording should not panic and should be enabled
	if !r.IsEnabled() {
		t.Error("recorder should still be enabled")
	}
}

func TestDebugRecorderRecordEvent(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	r := GetDebugRecorder()

	err := r.Start("watch", "xterm", "/dev/pts/3", 80, 24)
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}
	defer r.Stop(0)

	r.RecordEvent("KEY", "key=enter")
	r.RecordEvent("RESIZE", "width=100 height=40")

	if !r.IsEnabled() {
		t.Error("recorder should still be enabled after events")
	}
}

func TestDebugRecorderCreatesIssuesDir(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	// Remove docs/issues if it exists to test creation
	os.RemoveAll("docs/issues")

	r := GetDebugRecorder()
	err := r.Start("watch", "xterm", "/dev/pts/4", 80, 24)
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}
	defer r.Stop(0)

	// Check that docs/issues directory was created
	if _, err := os.Stat("docs/issues"); os.IsNotExist(err) {
		t.Error("docs/issues directory should be created")
	}
}

func TestDebugRecorderFileContent(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	// Remove existing debug files
	files, _ := filepath.Glob("docs/issues/debug_*.txt")
	for _, f := range files {
		os.Remove(f)
	}

	r := GetDebugRecorder()
	err := r.Start("watch", "xterm-256color", "/dev/pts/5", 183, 30)
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	r.RecordFrame("frame 1")
	r.RecordEvent("KEY", "key=q")
	r.RecordFrame("frame 2")

	r.Stop(0)

	// Find the created file
	files, _ = filepath.Glob("docs/issues/debug_*.txt")
	if len(files) == 0 {
		t.Fatal("no debug file was created")
	}

	content, err := os.ReadFile(files[0])
	if err != nil {
		t.Fatalf("failed to read debug file: %v", err)
	}

	contentStr := string(content)

	if !strings.Contains(contentStr, "Session started") {
		t.Error("file should contain session start header")
	}
	if !strings.Contains(contentStr, "COMMAND=\"watch\"") {
		t.Error("file should contain command name")
	}
	if !strings.Contains(contentStr, "TERM=\"xterm-256color\"") {
		t.Error("file should contain TERM")
	}
	if !strings.Contains(contentStr, "COLUMNS=183") {
		t.Error("file should contain columns")
	}
	if !strings.Contains(contentStr, "frame 1") {
		t.Error("file should contain first frame")
	}
	if !strings.Contains(contentStr, "frame 2") {
		t.Error("file should contain second frame")
	}
	if !strings.Contains(contentStr, "KEY") {
		t.Error("file should contain KEY event")
	}
	if !strings.Contains(contentStr, "Session ended") {
		t.Error("file should contain session end footer")
	}
	if !strings.Contains(contentStr, "COMMAND_EXIT_CODE=0") {
		t.Error("file should contain exit code")
	}

	// Clean up
	os.Remove(files[0])
}

func TestDebugRecorderMultipleStart(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	r := GetDebugRecorder()

	err := r.Start("cmd1", "xterm", "/dev/pts/6", 80, 24)
	if err != nil {
		t.Fatalf("First start failed: %v", err)
	}

	// Second start should be ignored (already enabled)
	err = r.Start("cmd2", "vt100", "/dev/pts/7", 100, 40)
	if err != nil {
		t.Error("Second start should not fail")
	}

	r.Stop(0)
}

func TestDebugRecorderDisabledByDefault(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	r := GetDebugRecorder()
	if r.IsEnabled() {
		t.Error("recorder should be disabled by default")
	}

	// Recording when disabled should not panic
	r.RecordFrame("should not crash")
	r.RecordEvent("KEY", "should not crash")
}

func TestEnableDisableDebugRecorder(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	// Remove existing debug files
	files, _ := filepath.Glob("docs/issues/debug_*.txt")
	for _, f := range files {
		os.Remove(f)
	}

	err := EnableDebugRecorder("watch", "xterm", "/dev/pts/8", 80, 24)
	if err != nil {
		t.Fatalf("EnableDebugRecorder failed: %v", err)
	}

	if !GetDebugRecorder().IsEnabled() {
		t.Error("recorder should be enabled")
	}

	DisableDebugRecorder(0)

	if GetDebugRecorder().IsEnabled() {
		t.Error("recorder should be disabled")
	}

	// Clean up any created files
	files, _ = filepath.Glob("docs/issues/debug_*.txt")
	for _, f := range files {
		os.Remove(f)
	}
}

func TestDebugRecorderViewIntegration(t *testing.T) {
	// Clean up
	recorder = nil
	recorderOnce = sync.Once{}

	// Remove existing debug files
	files, _ := filepath.Glob("docs/issues/debug_*.txt")
	for _, f := range files {
		os.Remove(f)
	}

	err := EnableDebugRecorder("watch", "xterm", "/dev/pts/9", 120, 40)
	if err != nil {
		t.Fatalf("EnableDebugRecorder failed: %v", err)
	}
	defer DisableDebugRecorder(0)

	// Create a model and render a view
	m := makeTestModelWithRuns()
	view := m.View()

	if view == "" {
		t.Error("view should not be empty")
	}

	// The view should have been recorded
	if !GetDebugRecorder().IsEnabled() {
		t.Error("recorder should still be enabled")
	}

	// Clean up
	files, _ = filepath.Glob("docs/issues/debug_*.txt")
	for _, f := range files {
		os.Remove(f)
	}
}
