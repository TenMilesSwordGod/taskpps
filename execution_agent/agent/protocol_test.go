package agent

import (
	"encoding/json"
	"testing"
)

// TestHandshakeRequestFields 是唯一保留的协议序列化测试：
// 它断言 Marshal 后的 JSON 原始 key 名（agent_id/agent_pid 等），
// 一旦 json tag 被改错（如 agent_id 写成 agentId）即可捕获。
// 纯 Marshal→Unmarshal 对称 round-trip 测试只验证 encoding/json 自身，
// 已按审计报告删除。
func TestHandshakeRequestFields(t *testing.T) {
	req := HandshakeRequest{
		AgentID:  "agent-01",
		Secret:   "secret",
		Version:  "1.0.0",
		Hostname: "myhost",
		AgentPID: 9999,
		OS:       "linux",
		Arch:     "amd64",
	}

	data, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if raw["agent_id"] != "agent-01" {
		t.Errorf("expected agent_id 'agent-01', got %v", raw["agent_id"])
	}
	if raw["hostname"] != "myhost" {
		t.Errorf("expected hostname 'myhost', got %v", raw["hostname"])
	}
	if int(raw["agent_pid"].(float64)) != 9999 {
		t.Errorf("expected agent_pid 9999, got %v", raw["agent_pid"])
	}
	if raw["version"] != "1.0.0" {
		t.Errorf("expected version '1.0.0', got %v", raw["version"])
	}
	if raw["os"] != "linux" || raw["arch"] != "amd64" {
		t.Errorf("expected os/arch linux/amd64, got %v/%v", raw["os"], raw["arch"])
	}
	if _, ok := raw["secret"]; !ok {
		t.Error("expected secret key in handshake payload")
	}
}
