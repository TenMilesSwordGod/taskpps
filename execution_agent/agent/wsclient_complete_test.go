package agent

import (
	"testing"
)

// wsclient_complete_test.go — complete_request 消息分发与响应发送。
// handleMessage 不依赖真实连接，可直接构造 WsClient 验证分发逻辑。

func TestWsClient_HandleCompleteRequest(t *testing.T) {
	c := NewWsClient("ws://test", "agent-1", "secret", "host", 1, "linux", "amd64")

	got := make(chan CompleteRequest, 1)
	c.OnComplete = func(req CompleteRequest) {
		got <- req
	}

	c.handleMessage(Message{
		Type: MsgTypeCompleteRequest,
		Data: map[string]interface{}{
			"request_id": "req-9",
			"line":       "cd ./my d",
			"cursor":     10,
			"cwd":        "/tmp",
		},
	})

	select {
	case req := <-got:
		if req.RequestID != "req-9" {
			t.Errorf("expected req-9, got %s", req.RequestID)
		}
		if req.Line != "cd ./my d" {
			t.Errorf("expected line, got %s", req.Line)
		}
		if req.Cursor != 10 {
			t.Errorf("expected 10, got %d", req.Cursor)
		}
		if req.Cwd != "/tmp" {
			t.Errorf("expected /tmp, got %s", req.Cwd)
		}
	default:
		t.Fatal("expected OnComplete to be invoked")
	}
}

func TestWsClient_HandleCompleteRequest_Malformed(t *testing.T) {
	c := NewWsClient("ws://test", "agent-1", "secret", "host", 1, "linux", "amd64")

	invoked := false
	c.OnComplete = func(req CompleteRequest) {
		invoked = true
	}

	// 畸形 data 不应崩溃，也不应调用回调（日志记录后忽略）
	c.handleMessage(Message{
		Type: MsgTypeCompleteRequest,
		Data: "not-a-map",
	})

	if invoked {
		t.Error("expected OnComplete not to be invoked for malformed data")
	}
}
