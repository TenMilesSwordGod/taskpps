package agent

import (
	"encoding/json"
	"testing"
)

func TestMessageSerialization(t *testing.T) {
	msg := Message{
		Type: MsgTypeHandshakeRequest,
		Data: HandshakeRequest{
			AgentID: "test-agent",
			Secret:  "test-secret",
			Version: ProtocolVersion,
		},
	}

	data, err := json.Marshal(msg)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded Message
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.Type != MsgTypeHandshakeRequest {
		t.Errorf("expected %s, got %s", MsgTypeHandshakeRequest, decoded.Type)
	}
}

func TestExecCommandSerialization(t *testing.T) {
	cmd := ExecCommand{
		CommandID: "cmd-001",
		Command:   "echo hello",
		Env:       map[string]string{"KEY": "VAL"},
		Cwd:       "/tmp",
		Timeout:   30,
	}

	data, err := json.Marshal(cmd)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded ExecCommand
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.CommandID != "cmd-001" {
		t.Errorf("expected cmd-001, got %s", decoded.CommandID)
	}
	if decoded.Timeout != 30 {
		t.Errorf("expected 30, got %d", decoded.Timeout)
	}
}

func TestExecResultSerialization(t *testing.T) {
	result := ExecResult{
		CommandID:  "cmd-001",
		ExitCode:   -9,
		SignalName: "SIGKILL",
		DurationMs: 1500,
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded ExecResult
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.ExitCode != -9 {
		t.Errorf("expected -9, got %d", decoded.ExitCode)
	}
	if decoded.SignalName != "SIGKILL" {
		t.Errorf("expected SIGKILL, got %s", decoded.SignalName)
	}
	if decoded.DurationMs != 1500 {
		t.Errorf("expected 1500, got %d", decoded.DurationMs)
	}
}

func TestExecResultSuccess(t *testing.T) {
	result := ExecResult{
		CommandID:  "cmd-002",
		ExitCode:   0,
		DurationMs: 100,
	}

	data, err := json.Marshal(result)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var decoded ExecResult
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if decoded.ExitCode != 0 {
		t.Errorf("expected 0, got %d", decoded.ExitCode)
	}
	if decoded.SignalName != "" {
		t.Errorf("expected empty signal_name, got %s", decoded.SignalName)
	}
}
