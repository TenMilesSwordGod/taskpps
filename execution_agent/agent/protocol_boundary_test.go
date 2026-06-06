package agent

import (
	"testing"
)

func TestMessageType_Values(t *testing.T) {
	tests := []struct {
		name     string
		expected MessageType
		value    string
	}{
		{"handshake_request", MsgTypeHandshakeRequest, "handshake_request"},
		{"handshake_response", MsgTypeHandshakeResponse, "handshake_response"},
		{"exec_command", MsgTypeExecCommand, "exec_command"},
		{"cancel_command", MsgTypeCancelCommand, "cancel_command"},
		{"stdout_chunk", MsgTypeStdoutChunk, "stdout_chunk"},
		{"stderr_chunk", MsgTypeStderrChunk, "stderr_chunk"},
		{"exec_result", MsgTypeExecResult, "exec_result"},
		{"heartbeat_request", MsgTypeHeartbeatRequest, "heartbeat_request"},
		{"heartbeat_response", MsgTypeHeartbeatResponse, "heartbeat_response"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if string(tt.expected) != tt.value {
				t.Errorf("expected %s, got %s", tt.value, tt.expected)
			}
		})
	}
}

func TestProtocolVersion(t *testing.T) {
	if ProtocolVersion != "1.0.0" {
		t.Errorf("expected 1.0.0, got %s", ProtocolVersion)
	}
}

func TestMessage_Empty(t *testing.T) {
	msg := Message{}
	if msg.Type != "" {
		t.Errorf("expected empty type, got %s", msg.Type)
	}
	if msg.Data != nil {
		t.Errorf("expected nil data, got %v", msg.Data)
	}
}

func TestHandshakeRequest_Defaults(t *testing.T) {
	req := HandshakeRequest{}
	if req.AgentID != "" {
		t.Errorf("expected empty agent_id, got %s", req.AgentID)
	}
}

func TestHandshakeRequest_Full(t *testing.T) {
	req := HandshakeRequest{
		AgentID:  "agent-1",
		Secret:   "secret123",
		Version:  "1.0.0",
		Hostname: "test-host",
		AgentPID: 1234,
		OS:       "linux",
		Arch:     "amd64",
	}
	if req.AgentID != "agent-1" {
		t.Errorf("expected agent-1, got %s", req.AgentID)
	}
	if req.Secret != "secret123" {
		t.Errorf("expected secret123, got %s", req.Secret)
	}
	if req.AgentPID != 1234 {
		t.Errorf("expected 1234, got %d", req.AgentPID)
	}
}

func TestHandshakeResponse_Fields(t *testing.T) {
	resp := HandshakeResponse{
		AgentID:      "agent-1",
		Hostname:     "test-host",
		AgentVersion: "1.0.0",
		AgentPID:     5678,
	}
	if resp.AgentID != "agent-1" {
		t.Errorf("expected agent-1, got %s", resp.AgentID)
	}
	if resp.AgentPID != 5678 {
		t.Errorf("expected 5678, got %d", resp.AgentPID)
	}
}

func TestExecCommand_Defaults(t *testing.T) {
	cmd := ExecCommand{}
	if cmd.CommandID != "" {
		t.Errorf("expected empty command_id, got %s", cmd.CommandID)
	}
	if cmd.Command != "" {
		t.Errorf("expected empty command, got %s", cmd.Command)
	}
}

func TestExecCommand_Full(t *testing.T) {
	cmd := ExecCommand{
		CommandID: "cmd-1",
		Command:   "echo hello",
		Env:       map[string]string{"KEY": "VAL"},
		Cwd:       "/tmp",
		Timeout:   30,
	}
	if cmd.CommandID != "cmd-1" {
		t.Errorf("expected cmd-1, got %s", cmd.CommandID)
	}
	if cmd.Command != "echo hello" {
		t.Errorf("expected echo hello, got %s", cmd.Command)
	}
	if cmd.Env["KEY"] != "VAL" {
		t.Errorf("expected VAL, got %s", cmd.Env["KEY"])
	}
	if cmd.Cwd != "/tmp" {
		t.Errorf("expected /tmp, got %s", cmd.Cwd)
	}
	if cmd.Timeout != 30 {
		t.Errorf("expected 30, got %d", cmd.Timeout)
	}
}

func TestCancelCommand_Fields(t *testing.T) {
	cmd := CancelCommand{
		CommandID: "cmd-1",
	}
	if cmd.CommandID != "cmd-1" {
		t.Errorf("expected cmd-1, got %s", cmd.CommandID)
	}
}

func TestStdoutChunk_Fields(t *testing.T) {
	chunk := StdoutChunk{
		CommandID: "cmd-1",
		Data:      "hello world",
	}
	if chunk.CommandID != "cmd-1" {
		t.Errorf("expected cmd-1, got %s", chunk.CommandID)
	}
	if chunk.Data != "hello world" {
		t.Errorf("expected hello world, got %s", chunk.Data)
	}
}

func TestStderrChunk_Fields(t *testing.T) {
	chunk := StderrChunk{
		CommandID: "cmd-1",
		Data:      "error message",
	}
	if chunk.Data != "error message" {
		t.Errorf("expected error message, got %s", chunk.Data)
	}
}

func TestExecResult_Success(t *testing.T) {
	result := ExecResult{
		CommandID:  "cmd-1",
		ExitCode:   0,
		DurationMs: 150,
	}
	if result.ExitCode != 0 {
		t.Errorf("expected 0, got %d", result.ExitCode)
	}
	if result.DurationMs != 150 {
		t.Errorf("expected 150, got %d", result.DurationMs)
	}
}

func TestExecResult_Failure(t *testing.T) {
	result := ExecResult{
		CommandID:  "cmd-1",
		ExitCode:   1,
		DurationMs: 100,
		Error:      "command failed",
	}
	if result.ExitCode != 1 {
		t.Errorf("expected 1, got %d", result.ExitCode)
	}
	if result.Error != "command failed" {
		t.Errorf("expected command failed, got %s", result.Error)
	}
}

func TestExecResult_Signaled(t *testing.T) {
	result := ExecResult{
		CommandID:  "cmd-1",
		ExitCode:   -9,
		SignalName: "SIGKILL",
		DurationMs: 50,
	}
	if result.SignalName != "SIGKILL" {
		t.Errorf("expected SIGKILL, got %s", result.SignalName)
	}
	if result.ExitCode != -9 {
		t.Errorf("expected -9, got %d", result.ExitCode)
	}
}