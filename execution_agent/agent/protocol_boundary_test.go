package agent

import (
	"testing"
)

// 本文件保留的测试只覆盖"对外协议常量"这一真实契约。
// 纯 struct 字段回显用例（构造→断言等于刚赋的值）已按审计报告删除，
// 因为字段读写由 Go 语言保证，无法捕获任何回归。

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
		{"complete_request", MsgTypeCompleteRequest, "complete_request"},
		{"complete_result", MsgTypeCompleteResult, "complete_result"},
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
