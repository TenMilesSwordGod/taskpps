package agent

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// testWSServer 是覆盖 wsclient 行为的最小真实 WebSocket 服务端。
// 为什么不用 mock 连接：Connect/sendMsg/handleMessage 的序列化、握手、
// 帧类型都发生在 gorilla 连接上，真实连接才能捕获协议与顺序回归。
type testWSServer struct {
	t        *testing.T
	server   *httptest.Server
	upgrader websocket.Upgrader
	attempts int32
	rejectN  int32

	mu   sync.Mutex
	conn *websocket.Conn
	msgs chan Message
}

func newTestWSServer(t *testing.T, rejectN int) *testWSServer {
	s := &testWSServer{
		t:       t,
		rejectN: int32(rejectN),
		msgs:    make(chan Message, 128),
	}
	s.upgrader = websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	s.server = httptest.NewServer(http.HandlerFunc(s.handle))
	t.Cleanup(s.server.Close)
	return s
}

func (s *testWSServer) handle(w http.ResponseWriter, r *http.Request) {
	if atomic.AddInt32(&s.attempts, 1) <= s.rejectN {
		// 模拟服务端不可用：Dial 立即失败，避免测试等待真实网络超时
		http.Error(w, "reject for test", http.StatusInternalServerError)
		return
	}
	conn, err := s.upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	s.mu.Lock()
	s.conn = conn
	s.mu.Unlock()

	go func() {
		defer conn.Close()
		for {
			var msg Message
			if err := conn.ReadJSON(&msg); err != nil {
				return
			}
			select {
			case s.msgs <- msg:
			case <-time.After(time.Second):
				// 客户端发得太快时也不能阻塞读取循环
			}
		}
	}()
}

func (s *testWSServer) url() string {
	return "ws" + strings.TrimPrefix(s.server.URL, "http")
}

func (s *testWSServer) attemptsCount() int {
	return int(atomic.LoadInt32(&s.attempts))
}

// send 向已升级的连接推送一条消息（用于模拟服务端主动下发）。
func (s *testWSServer) send(t *testing.T, msg Message) {
	t.Helper()
	s.mu.Lock()
	conn := s.conn
	s.mu.Unlock()
	if conn == nil {
		t.Fatal("测试服务端尚未建立连接")
	}
	if err := conn.WriteJSON(msg); err != nil {
		t.Fatalf("服务端写消息失败: %v", err)
	}
}

// closeClientConn 强制关闭服务端侧连接，模拟网络中断。
func (s *testWSServer) closeClientConn() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.conn != nil {
		s.conn.Close()
	}
}

func (s *testWSServer) waitMessage(t *testing.T, timeout time.Duration) Message {
	t.Helper()
	select {
	case msg := <-s.msgs:
		return msg
	case <-time.After(timeout):
		t.Fatalf("等待客户端消息超时 (attempts=%d)", s.attemptsCount())
		return Message{}
	}
}

type sleepRecorder struct {
	mu     sync.Mutex
	delays []time.Duration
}

func (r *sleepRecorder) sleep(d time.Duration) {
	r.mu.Lock()
	r.delays = append(r.delays, d)
	r.mu.Unlock()
}

func (r *sleepRecorder) recorded() []time.Duration {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]time.Duration(nil), r.delays...)
}

func (r *sleepRecorder) len() int {
	r.mu.Lock()
	defer r.mu.Unlock()
	return len(r.delays)
}

// newTestClient 指向测试服务端；sleep 替换为记录器，避免真实退避等待。
func newTestClient(t *testing.T, url string) (*WsClient, *sleepRecorder) {
	t.Helper()
	c := NewWsClient(url, "agent-test", "secret", "host-test", 4242, "linux", "amd64")
	rec := &sleepRecorder{}
	c.sleep = rec.sleep
	return c, rec
}

func decodeData(t *testing.T, msg Message, target interface{}) {
	t.Helper()
	data, err := json.Marshal(msg.Data)
	if err != nil {
		t.Fatalf("marshal message data: %v", err)
	}
	if err := json.Unmarshal(data, target); err != nil {
		t.Fatalf("unmarshal message data: %v", err)
	}
}

func TestWsClient_DefaultTimeouts(t *testing.T) {
	// 90s 读超时与 15s 心跳是服务端超时策略的契约，改坏必须被发现
	c := NewWsClient("ws://test", "a", "s", "h", 1, "linux", "amd64")
	if c.readTimeout != 90*time.Second {
		t.Errorf("default readTimeout = %v, want 90s", c.readTimeout)
	}
	if c.heartbeatEvery != 15*time.Second {
		t.Errorf("default heartbeatEvery = %v, want 15s", c.heartbeatEvery)
	}
}

// TestWsClient_ConnectSendsHandshake 验证连接建立后的首个帧是握手请求，
// 且重复 Connect 为 no-op。协议首帧错乱会导致服务端拒绝认领该 agent。
func TestWsClient_ConnectSendsHandshake(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())

	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	if !c.IsConnected() {
		t.Fatal("expected IsConnected()=true after Connect")
	}

	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeHandshakeRequest {
		t.Fatalf("first message type = %s, want %s", msg.Type, MsgTypeHandshakeRequest)
	}
	var hs HandshakeRequest
	decodeData(t, msg, &hs)
	if hs.AgentID != "agent-test" || hs.Secret != "secret" || hs.Hostname != "host-test" {
		t.Errorf("unexpected handshake identity: %+v", hs)
	}
	if hs.AgentPID != 4242 || hs.OS != "linux" || hs.Arch != "amd64" {
		t.Errorf("unexpected handshake metadata: %+v", hs)
	}
	if hs.Version != ProtocolVersion {
		t.Errorf("handshake version = %q, want %q", hs.Version, ProtocolVersion)
	}

	// 已连接时重复 Connect 应为 no-op，不得重复发起握手
	if err := c.Connect(); err != nil {
		t.Fatalf("second Connect() error: %v", err)
	}
	if got := srv.attemptsCount(); got != 1 {
		t.Errorf("dial attempts = %d, want 1 after redundant Connect", got)
	}
}

// TestWsClient_ReadHandshakeResponse 验证服务端握手响应的解码字段。
func TestWsClient_ReadHandshakeResponse(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second) // 消费握手请求

	srv.send(t, Message{Type: MsgTypeHandshakeResponse, Data: HandshakeResponse{
		AgentID:      "agent-test",
		Hostname:     "host-test",
		AgentVersion: "1.2.3",
		AgentPID:     777,
	}})

	resp, err := c.readHandshakeResponse()
	if err != nil {
		t.Fatalf("readHandshakeResponse() error: %v", err)
	}
	if resp.AgentID != "agent-test" || resp.AgentVersion != "1.2.3" || resp.AgentPID != 777 {
		t.Errorf("unexpected handshake response: %+v", resp)
	}
}

// TestWsClient_ReadHandshakeResponseWrongType 保证非握手帧不会被误当作握手成功。
func TestWsClient_ReadHandshakeResponseWrongType(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second)

	srv.send(t, Message{Type: MsgTypeHeartbeatRequest, Data: map[string]string{}})
	if _, err := c.readHandshakeResponse(); err == nil {
		t.Fatal("expected error for unexpected handshake message type")
	}
}

func TestWsClient_ReconnectBackoffSequenceCapsAt60s(t *testing.T) {
	// 服务端永远拒绝：完整走完 1/2/4/8/16/30/60s 并验证 60s 封顶
	srv := newTestWSServer(t, 1<<30)
	c, rec := newTestClient(t, srv.url())
	c.sleep = func(d time.Duration) {
		rec.sleep(d)
		if rec.len() >= 8 {
			c.Close() // 记录满 8 次后收掉客户端，使 tryReconnect 退出
		}
	}

	c.tryReconnect()

	want := []time.Duration{
		1 * time.Second, 2 * time.Second, 4 * time.Second, 8 * time.Second,
		16 * time.Second, 30 * time.Second, 60 * time.Second, 60 * time.Second,
	}
	got := rec.recorded()
	if len(got) != len(want) {
		t.Fatalf("backoff sequence length = %d (%v), want %d", len(got), got, len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("backoff[%d] = %v, want %v (full: %v)", i, got[i], want[i], got)
		}
	}
}

// TestWsClient_ReadTimeoutTriggersReconnect 用可注入的 readTimeout 验证
// "读超时 → 断开 → 进入重连退避"的完整链路（默认 90s 无法在测试中真实等待）。
func TestWsClient_ReadTimeoutTriggersReconnect(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, rec := newTestClient(t, srv.url())
	c.readTimeout = 150 * time.Millisecond
	c.heartbeatEvery = time.Hour // 本用例只验证读超时路径，关闭心跳干扰

	release := make(chan struct{})
	c.sleep = func(d time.Duration) {
		rec.sleep(d)
		<-release // 卡住重连循环，便于断言"已断开且进入退避"
	}

	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	c.Run()
	defer func() {
		close(release)
		c.Close()
	}()

	deadline := time.Now().Add(3 * time.Second)
	for rec.len() == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if rec.len() == 0 {
		t.Fatal("read timeout did not trigger reconnect backoff")
	}
	if got := rec.recorded()[0]; got != 1*time.Second {
		t.Errorf("first reconnect backoff = %v, want 1s", got)
	}
	if c.IsConnected() {
		t.Error("expected connection marked disconnected after read timeout")
	}
}

// TestWsClient_PendingResultsFlushAfterReconnect 验证断线期间缓存的 exec_result
// 在重连后原样补发，避免命令结果永久丢失。
func TestWsClient_PendingResultsFlushAfterReconnect(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())

	result := ExecResult{CommandID: "cmd-pending", ExitCode: 7, DurationMs: 12}
	if err := c.SendResult(result); err == nil {
		t.Fatal("expected SendResult error when not connected")
	}
	c.mu.Lock()
	pending := len(c.pendingResults)
	c.mu.Unlock()
	if pending != 1 {
		t.Fatalf("pendingResults = %d, want 1", pending)
	}

	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second) // 握手

	c.flushPendingResults()

	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeExecResult {
		t.Fatalf("flushed message type = %s, want %s", msg.Type, MsgTypeExecResult)
	}
	var flushed ExecResult
	decodeData(t, msg, &flushed)
	if flushed.CommandID != result.CommandID || flushed.ExitCode != result.ExitCode {
		t.Errorf("flushed result = %+v, want %+v", flushed, result)
	}

	c.mu.Lock()
	remaining := len(c.pendingResults)
	c.mu.Unlock()
	if remaining != 0 {
		t.Errorf("pendingResults after flush = %d, want 0", remaining)
	}
}

// TestWsClient_FlushPendingResultsFailureRequeues 验证补发失败的结果会重新入队，
// 而不是被静默丢弃。
func TestWsClient_FlushPendingResultsFailureRequeues(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())

	result := ExecResult{CommandID: "cmd-lost", ExitCode: 3}
	_ = c.SendResult(result) // 未连接 → 入 pending

	c.flushPendingResults() // 仍未连接 → 补发失败，必须重新入队

	c.mu.Lock()
	pending := append([]ExecResult(nil), c.pendingResults...)
	c.mu.Unlock()
	if len(pending) != 1 || pending[0].CommandID != "cmd-lost" {
		t.Fatalf("pendingResults after failed flush = %+v, want the original result requeued", pending)
	}
}

// TestWsClient_SendCompleteDroppedWhenDisconnected 固化补全结果的断线策略：
// 直接报错丢弃、不进入 pendingResults（补全是瞬时交互，不做断线重发）。
func TestWsClient_SendCompleteDroppedWhenDisconnected(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())

	// 补全是瞬时交互，断线必须直接失败且不得进入 pendingResults 重发队列
	if err := c.SendComplete(CompleteResult{RequestID: "req-1", Candidates: []string{"ls"}}); err == nil {
		t.Fatal("expected SendComplete error when not connected")
	}
	c.mu.Lock()
	pending := len(c.pendingResults)
	c.mu.Unlock()
	if pending != 0 {
		t.Fatalf("SendComplete must not be queued, pendingResults = %d", pending)
	}

	// 连接后同一调用必须能正常送达
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second) // 握手
	if err := c.SendComplete(CompleteResult{RequestID: "req-2", Candidates: []string{"ls"}}); err != nil {
		t.Fatalf("SendComplete after connect error: %v", err)
	}
	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeCompleteResult {
		t.Fatalf("message type = %s, want %s", msg.Type, MsgTypeCompleteResult)
	}
	var got CompleteResult
	decodeData(t, msg, &got)
	if got.RequestID != "req-2" {
		t.Errorf("complete result request_id = %q, want req-2", got.RequestID)
	}
}

// TestWsClient_HeartbeatLoopSendsHeartbeats 验证心跳循环按配置间隔发出心跳帧。
func TestWsClient_HeartbeatLoopSendsHeartbeats(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	c.heartbeatEvery = 40 * time.Millisecond

	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second) // 握手

	go c.heartbeatLoop()
	defer c.Close()

	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeHeartbeatResponse {
		t.Fatalf("heartbeat message type = %s, want %s", msg.Type, MsgTypeHeartbeatResponse)
	}
}

// TestWsClient_HandleDisconnectMarksDisconnectedAndCachesResults 验证连接释放后
// IsConnected=false，且后续结果进入待补发缓存。
func TestWsClient_HandleDisconnectMarksDisconnectedAndCachesResults(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second)

	c.handleDisconnect()

	if c.IsConnected() {
		t.Error("expected IsConnected()=false after handleDisconnect")
	}
	c.mu.Lock()
	conn := c.conn
	c.mu.Unlock()
	if conn != nil {
		t.Error("expected conn released after handleDisconnect")
	}

	// 断线期间结果进入缓存，等待重连补发
	if err := c.SendResult(ExecResult{CommandID: "after-disconnect", ExitCode: 1}); err == nil {
		t.Error("expected SendResult error when disconnected")
	}
	c.mu.Lock()
	pending := len(c.pendingResults)
	c.mu.Unlock()
	if pending != 1 {
		t.Errorf("pendingResults = %d, want 1", pending)
	}
}

// TestWsClient_CloseStopsReconnect 验证 Close 后不再产生新的拨号，避免进程退出时
// 重连 goroutine 泄漏/反复建连。
func TestWsClient_CloseStopsReconnect(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	c.Run()

	before := srv.attemptsCount()
	c.Close()
	if c.IsConnected() {
		t.Error("expected IsConnected()=false after Close")
	}

	time.Sleep(200 * time.Millisecond)
	if after := srv.attemptsCount(); after != before {
		t.Errorf("dial attempts after Close = %d, want no new attempts (before=%d)", after, before)
	}
}

// TestWsClient_HandleMessageDispatchesCommands 验证 exec_command/cancel_command
// 能正确解码并分发到对应回调。
func TestWsClient_HandleMessageDispatchesCommands(t *testing.T) {
	c := NewWsClient("ws://test", "a", "s", "h", 1, "linux", "amd64")

	commandCh := make(chan ExecCommand, 1)
	cancelCh := make(chan string, 1)
	c.OnCommand = func(cmd ExecCommand) { commandCh <- cmd }
	c.OnCancel = func(id string) { cancelCh <- id }

	c.handleMessage(Message{Type: MsgTypeExecCommand, Data: ExecCommand{
		CommandID: "cmd-9",
		Command:   "echo hi",
		Cwd:       "/tmp",
		Timeout:   5,
	}})
	select {
	case cmd := <-commandCh:
		if cmd.CommandID != "cmd-9" || cmd.Command != "echo hi" || cmd.Timeout != 5 {
			t.Errorf("unexpected exec command: %+v", cmd)
		}
	default:
		t.Fatal("OnCommand was not invoked")
	}

	c.handleMessage(Message{Type: MsgTypeCancelCommand, Data: CancelCommand{CommandID: "cmd-9"}})
	select {
	case id := <-cancelCh:
		if id != "cmd-9" {
			t.Errorf("cancel command id = %q, want cmd-9", id)
		}
	default:
		t.Fatal("OnCancel was not invoked")
	}
}

// TestWsClient_HandleMessageMalformedFrames 验证畸形帧不崩溃、不误触发回调，
// 且 ping 即使携带坏数据仍能维持心跳语义。
func TestWsClient_HandleMessageMalformedFrames(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second)

	var commandCalls, cancelCalls int32
	c.OnCommand = func(ExecCommand) { atomic.AddInt32(&commandCalls, 1) }
	c.OnCancel = func(string) { atomic.AddInt32(&cancelCalls, 1) }

	// 三类畸形帧都不得调用回调，也不得 panic
	c.handleMessage(Message{Type: MsgTypeExecCommand, Data: "not-a-map"})
	c.handleMessage(Message{Type: MsgTypeExecCommand, Data: map[string]interface{}{"command_id": 123}})
	c.handleMessage(Message{Type: MsgTypeCancelCommand, Data: 12345})

	if got := atomic.LoadInt32(&commandCalls); got != 0 {
		t.Errorf("malformed exec_command invoked OnCommand %d time(s)", got)
	}
	if got := atomic.LoadInt32(&cancelCalls); got != 0 {
		t.Errorf("malformed cancel_command invoked OnCancel %d time(s)", got)
	}

	// ping 携带畸形 data 时仍应回答心跳，保证连接活性判断不被坏帧影响
	c.handleMessage(Message{Type: MsgTypePing, Data: "garbage"})
	msg := srv.waitMessage(t, 2*time.Second)
	if msg.Type != MsgTypeHeartbeatResponse {
		t.Fatalf("ping response type = %s, want %s", msg.Type, MsgTypeHeartbeatResponse)
	}
}

// TestWsClient_SendFailureMarksDisconnected 验证写失败会把连接标记为断开，
// 使 readLoop 进入重连流程。
func TestWsClient_SendFailureMarksDisconnected(t *testing.T) {
	srv := newTestWSServer(t, 0)
	c, _ := newTestClient(t, srv.url())
	if err := c.Connect(); err != nil {
		t.Fatalf("Connect() error: %v", err)
	}
	srv.waitMessage(t, 2*time.Second)

	srv.closeClientConn()
	// 写失败可能滞后于对端关闭，重试几次直到发送报错
	var sendErr error
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if sendErr = c.SendStdout("cmd-1", "hello"); sendErr != nil {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if sendErr == nil {
		t.Fatal("expected send error after server closed the connection")
	}
	if c.IsConnected() {
		t.Error("expected connection marked disconnected after send failure")
	}
}
