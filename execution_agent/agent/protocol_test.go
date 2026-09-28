package agent

import (
	"encoding/json"
	"testing"
)

func TestMessageSerialization(t *testing.T) {
	msg := Message{
		Type: MsgTypeHandshakeRequest,
		Data: HandshakeRequest{
			AgentID:  "test-agent",
			Secret:   "test-secret",
			Version:  ProtocolVersion,
			Hostname: "test-host",
			AgentPID: 12345,
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

func TestHandshakeRequestFields(t *testing.T) {
	req := HandshakeRequest{
		AgentID:  "agent-01",
		Secret:   "secret",
		Version:  "1.0.0",
		Hostname: "myhost",
		AgentPID: 9999,
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if raw["hostname"] != "myhost" {
		t.Errorf("expected hostname 'myhost', got %v", raw["hostname"])
	}
	if int(raw["agent_pid"].(float64)) != 9999 {
		t.Errorf("expected agent_pid 9999, got %v", raw["agent_pid"])
	}
}

func TestExecCommandSerialization(t *testing.T) {
	cmd := ExecCommand{
		CommandID: "cmd-001",
		Command:   "echo hello",
		Env:       map[string]string{"KEY": "VAL"},
		Cwd:       "/tmp",
		Timeout:   30,
		// v2 (2026-09): 服务器可按命令下发 shell，覆盖 agent 启动时的默认值
		Shell: "/bin/zsh",
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
	if decoded.Shell != "/bin/zsh" {
		t.Errorf("expected /bin/zsh, got %s", decoded.Shell)
	}
}

// TestExecCommandWithoutShellKeepsBackwardCompat 验证旧服务端报文（无 shell 字段）
// 仍可解析为空字符串，agent 端据此回退到启动时的 shell。
func TestExecCommandWithoutShellKeepsBackwardCompat(t *testing.T) {
	var decoded ExecCommand
	if err := json.Unmarshal([]byte(`{"command_id":"c","command":"echo hi","env":{},"cwd":"/tmp","timeout":5}`), &decoded); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if decoded.Shell != "" {
		t.Errorf("expected empty shell, got %s", decoded.Shell)
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
