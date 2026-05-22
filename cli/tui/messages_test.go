package tui

import (
	"errors"
	"testing"

	"github.com/taskpps/ppsctl/models"
)

func TestMessages(t *testing.T) {
	t.Run("runsFetchedMsg_success", func(t *testing.T) {
		runs := []models.Run{{ID: "1"}, {ID: "2"}}
		msg := runsFetchedMsg{runs: runs}
		if len(msg.runs) != 2 {
			t.Errorf("expected 2 runs, got %d", len(msg.runs))
		}
		if msg.err != nil {
			t.Errorf("expected nil error, got %v", msg.err)
		}
	})

	t.Run("runsFetchedMsg_error", func(t *testing.T) {
		err := errors.New("connection failed")
		msg := runsFetchedMsg{err: err}
		if msg.err == nil {
			t.Error("expected error")
		}
		if msg.runs != nil {
			t.Error("expected nil runs with error")
		}
	})

	t.Run("runFetchedMsg_success", func(t *testing.T) {
		run := &models.Run{ID: "abc"}
		msg := runFetchedMsg{run: run}
		if msg.run == nil {
			t.Error("expected run")
		}
		if msg.err != nil {
			t.Errorf("expected nil error, got %v", msg.err)
		}
	})

	t.Run("runFetchedMsg_error", func(t *testing.T) {
		err := errors.New("not found")
		msg := runFetchedMsg{err: err}
		if msg.err == nil {
			t.Error("expected error")
		}
		if msg.run != nil {
			t.Error("expected nil run with error")
		}
	})

	t.Run("logsFetchedMsg_success", func(t *testing.T) {
		logs := map[string]string{"task1": "log content"}
		msg := logsFetchedMsg{logs: logs}
		if len(msg.logs) != 1 {
			t.Errorf("expected 1 log, got %d", len(msg.logs))
		}
		if msg.err != nil {
			t.Errorf("expected nil error, got %v", msg.err)
		}
	})

	t.Run("logsFetchedMsg_error", func(t *testing.T) {
		err := errors.New("timeout")
		msg := logsFetchedMsg{err: err}
		if msg.err == nil {
			t.Error("expected error")
		}
		if msg.logs != nil {
			t.Error("expected nil logs with error")
		}
	})

	t.Run("tickMsg", func(t *testing.T) {
		msg := tickMsg{}
		_ = msg
	})
}