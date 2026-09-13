package agent

import (
	"os"
	"runtime"
	"sync"
	"syscall"
	"testing"
	"time"
)

// newTestAgentConfig 返回指向测试服务端的 AgentConfig。
func newTestAgentConfig(url string) *AgentConfig {
	return &AgentConfig{
		ServerURL: url,
		AgentID:   "agent-lifecycle",
		Secret:    "secret",
		Shell:     "/bin/sh",
		WorkDir:   "/tmp",
	}
}

// TestNewAgent_WiresConfigAndCallbacks 验证配置、进程元数据与三个命令回调
// 都被正确装配，任何漏接都会让远端命令无法执行。
func TestNewAgent_WiresConfigAndCallbacks(t *testing.T) {
	cfg := &AgentConfig{
		ServerURL: "ws://127.0.0.1:1/ws",
		AgentID:   "agent-x",
		Secret:    "s3cr3t",
		Shell:     "/bin/sh",
		WorkDir:   "/tmp",
	}
	a := NewAgent(cfg)

	if a.wsClient.url != cfg.ServerURL || a.wsClient.agentID != cfg.AgentID || a.wsClient.secret != cfg.Secret {
		t.Errorf("wsClient config not wired: %+v", a.wsClient)
	}
	hostname, _ := os.Hostname()
	if a.wsClient.hostname != hostname {
		t.Errorf("hostname = %q, want %q", a.wsClient.hostname, hostname)
	}
	if a.wsClient.agentPID != os.Getpid() {
		t.Errorf("agentPID = %d, want %d", a.wsClient.agentPID, os.Getpid())
	}
	if a.wsClient.osName != runtime.GOOS || a.wsClient.archName != runtime.GOARCH {
		t.Errorf("os/arch = %s/%s, want %s/%s", a.wsClient.osName, a.wsClient.archName, runtime.GOOS, runtime.GOARCH)
	}
	if a.wsClient.OnCommand == nil || a.wsClient.OnCancel == nil || a.wsClient.OnComplete == nil {
		t.Fatal("command/cancel/complete callbacks must be wired")
	}
	if a.executor == nil || a.stopCh == nil || a.sleep == nil {
		t.Fatal("executor/stopCh/sleep must be initialized")
	}
}

func TestAgentStartRetriesWithBackoffAndFails(t *testing.T) {
	srv := newTestWSServer(t, 1<<30) // 永远拒绝，走满重试次数
	a := NewAgent(newTestAgentConfig(srv.url()))

	var mu sync.Mutex
	var sleeps []time.Duration
	a.sleep = func(d time.Duration) {
		mu.Lock()
		sleeps = append(sleeps, d)
		mu.Unlock()
	}

	if err := a.Start(); err == nil {
		t.Fatal("expected Start() error when every connection attempt is rejected")
	}
	if got := srv.attemptsCount(); got != 5 {
		t.Errorf("connect attempts = %d, want 5", got)
	}

	// 现状语义：Start 在第 2..5 次尝试前分别等待 backoffs 中的 2/4/8/16s
	// （审计报告将该策略描述为 1/2/4/8/16，但实现是 sleep(backoffs[i])，
	// 首次重试等的是 2s。为遵守"不改变对外行为"，测试固化现状，偏差记入报告。）
	want := []time.Duration{2 * time.Second, 4 * time.Second, 8 * time.Second, 16 * time.Second}
	mu.Lock()
	got := append([]time.Duration(nil), sleeps...)
	mu.Unlock()
	if len(got) != len(want) {
		t.Fatalf("retry sleeps = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("retry sleep[%d] = %v, want %v (full: %v)", i, got[i], want[i], got)
		}
	}
}

// TestAgentStartConnectsAndStopCloses 覆盖生命周期主路径：Start 连接+握手，
// Stop 关闭 stopCh 并断开连接。
func TestAgentStartConnectsAndStopCloses(t *testing.T) {
	srv := newTestWSServer(t, 0)
	a := NewAgent(newTestAgentConfig(srv.url()))

	stopped := false
	t.Cleanup(func() {
		if !stopped {
			a.Stop()
		}
	})

	if err := a.Start(); err != nil {
		t.Fatalf("Start() error: %v", err)
	}
	if !a.wsClient.IsConnected() {
		t.Fatal("expected wsClient connected after Start")
	}
	// Start 成功路径必须完成握手
	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeHandshakeRequest {
		t.Errorf("first message type = %s, want handshake_request", msg.Type)
	}

	a.Stop()
	stopped = true

	select {
	case <-a.stopCh:
	default:
		t.Fatal("stopCh should be closed after Stop")
	}
	if a.wsClient.IsConnected() {
		t.Error("expected wsClient disconnected after Stop")
	}
}

// TestAgentHandleSignals 用真实 SIGTERM 验证信号处理会触发 Stop，
// 保证 daemon 能被 stop 命令正常关闭。
func TestAgentHandleSignals(t *testing.T) {
	a := NewAgent(&AgentConfig{ServerURL: "ws://127.0.0.1:1/ws", AgentID: "sig", Shell: "/bin/sh"})
	a.handleSignals()

	// handleSignals 同步注册信号处理后才返回，此处发送 SIGTERM 是安全的
	if err := syscall.Kill(os.Getpid(), syscall.SIGTERM); err != nil {
		t.Fatalf("发送 SIGTERM 失败: %v", err)
	}

	select {
	case <-a.stopCh:
	case <-time.After(3 * time.Second):
		t.Fatal("agent did not stop after SIGTERM")
	}
}

// TestAgentCallbacksDeliverMessages 验证 onStdout/onStderr/onResult 的发送链路，
// 对应远端终端输出与执行结果的用户可见行为。
func TestAgentCallbacksDeliverMessages(t *testing.T) {
	srv := newTestWSServer(t, 0)
	a := NewAgent(newTestAgentConfig(srv.url()))
	// 测试只验证回调发送链路，不需要启动重连循环
	if err := a.wsClient.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second) // 握手

	a.onStdout("cmd-1", "out-data")
	if msg := srv.waitMessage(t, 2*time.Second); msg.Type != MsgTypeStdoutChunk {
		t.Fatalf("stdout message type = %s", msg.Type)
	}

	a.onStderr("cmd-1", "err-data")
	if msg := srv.waitMessage(t, 2*time.Second); msg.Type != MsgTypeStderrChunk {
		t.Fatalf("stderr message type = %s", msg.Type)
	}

	a.onResult(ExecResult{CommandID: "cmd-1", ExitCode: 0, DurationMs: 9})
	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeExecResult {
		t.Fatalf("result message type = %s", msg.Type)
	}
	var result ExecResult
	decodeData(t, msg, &result)
	if result.CommandID != "cmd-1" || result.ExitCode != 0 || result.DurationMs != 9 {
		t.Errorf("unexpected exec result: %+v", result)
	}
}

func TestAgentSendResultFailureCachesPending(t *testing.T) {
	// 未连接时 onResult 的降级路径：记录错误并把结果放入 pendingResults，
	// stdout/stderr 只记日志、不得污染 pending 队列。
	a := NewAgent(newTestAgentConfig("ws://127.0.0.1:1/ws"))

	a.onStdout("cmd-2", "out")
	a.onStderr("cmd-2", "err")
	a.onResult(ExecResult{CommandID: "cmd-2", ExitCode: 2})

	a.wsClient.mu.Lock()
	pending := append([]ExecResult(nil), a.wsClient.pendingResults...)
	a.wsClient.mu.Unlock()
	if len(pending) != 1 {
		t.Fatalf("pendingResults = %+v, want exactly one cached exec_result", pending)
	}
	if pending[0].CommandID != "cmd-2" || pending[0].ExitCode != 2 {
		t.Errorf("cached result = %+v, want command cmd-2 exit 2", pending[0])
	}
}
