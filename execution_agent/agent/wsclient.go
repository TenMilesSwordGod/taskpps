package agent

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/taskpps/execution-agent/logger"
)

type WsClient struct {
	url       string
	agentID   string
	secret    string
	hostname  string
	agentPID  int
	osName    string
	archName  string
	conn      *websocket.Conn
	mu        sync.Mutex
	connected bool
	done      chan struct{}
	OnCommand func(ExecCommand)
	OnCancel  func(string)
	reconnect bool
}

func NewWsClient(url, agentID, secret, hostname string, agentPID int, osName, archName string) *WsClient {
	return &WsClient{
		url:       url,
		agentID:   agentID,
		secret:    secret,
		hostname:  hostname,
		agentPID:  agentPID,
		osName:    osName,
		archName:  archName,
		done:      make(chan struct{}),
		reconnect: true,
	}
}

func (c *WsClient) Connect() error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.connected {
		return nil
	}

	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}
	conn, _, err := dialer.Dial(c.url, nil)
	if err != nil {
		return fmt.Errorf("websocket dial %s: %w", c.url, err)
	}

	c.conn = conn
	c.connected = true

	if err := c.sendHandshake(); err != nil {
		conn.Close()
		c.connected = false
		return err
	}

	logger.Info("WebSocket connected to %s", c.url)
	return nil
}

func (c *WsClient) sendHandshake() error {
	msg := Message{
		Type: MsgTypeHandshakeRequest,
		Data: HandshakeRequest{
			AgentID:  c.agentID,
			Secret:   c.secret,
			Version:  ProtocolVersion,
			Hostname: c.hostname,
			AgentPID: c.agentPID,
			OS:       c.osName,
			Arch:     c.archName,
		},
	}
	return c.writeJSON(msg)
}

func (c *WsClient) readHandshakeResponse() (*HandshakeResponse, error) {
	var msg Message
	if err := c.conn.ReadJSON(&msg); err != nil {
		return nil, fmt.Errorf("read handshake response: %w", err)
	}
	if msg.Type != MsgTypeHandshakeResponse {
		return nil, fmt.Errorf("unexpected message type: %s", msg.Type)
	}
	data, _ := json.Marshal(msg.Data)
	var resp HandshakeResponse
	if err := json.Unmarshal(data, &resp); err != nil {
		return nil, fmt.Errorf("decode handshake response: %w", err)
	}
	return &resp, nil
}

func (c *WsClient) Run() {
	go c.heartbeatLoop()
	go c.readLoop()
}

func (c *WsClient) heartbeatLoop() {
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-c.done:
			return
		case <-ticker.C:
			c.mu.Lock()
			if !c.connected || c.conn == nil {
				c.mu.Unlock()
				continue
			}
			err := c.conn.WriteJSON(Message{Type: MsgTypeHeartbeatResponse, Data: map[string]string{}})
			c.mu.Unlock()
			if err != nil {
				logger.Warn("Heartbeat send failed: %v", err)
				c.handleDisconnect()
			}
		}
	}
}

func (c *WsClient) readLoop() {
	for {
		select {
		case <-c.done:
			return
		default:
		}

		c.mu.Lock()
		conn := c.conn
		c.mu.Unlock()

		if conn == nil {
			if c.reconnect {
				c.tryReconnect()
				continue
			}
			return
		}

		var msg Message
		// 设置读超时，快速检测连接断开（2 倍心跳间隔 + 缓冲）
		conn.SetReadDeadline(time.Now().Add(90 * time.Second))
		if err := conn.ReadJSON(&msg); err != nil {
			logger.Warn("WebSocket read error: %v", err)
			c.handleDisconnect()
			if c.reconnect {
				c.tryReconnect()
				continue
			}
			return
		}

		c.handleMessage(msg)
	}
}

func (c *WsClient) handleMessage(msg Message) {
	switch msg.Type {
	case MsgTypeExecCommand:
		data, _ := json.Marshal(msg.Data)
		var cmd ExecCommand
		if err := json.Unmarshal(data, &cmd); err != nil {
			logger.Error("Failed to decode exec_command: %v", err)
			return
		}
		logger.Info("Received exec_command: %s", cmd.CommandID)
		if c.OnCommand != nil {
			c.OnCommand(cmd)
		}

	case MsgTypeCancelCommand:
		data, _ := json.Marshal(msg.Data)
		var cancel CancelCommand
		if err := json.Unmarshal(data, &cancel); err != nil {
			logger.Error("Failed to decode cancel_command: %v", err)
			return
		}
		logger.Info("Received cancel_command: %s", cancel.CommandID)
		if c.OnCancel != nil {
			c.OnCancel(cancel.CommandID)
		}

	case MsgTypeHeartbeatRequest:
		c.SendHeartbeatResponse()

	case MsgTypePing:
		c.SendHeartbeatResponse()
	}
}

func (c *WsClient) SendStdout(commandID, data string) error {
	return c.sendMsg(MsgTypeStdoutChunk, StdoutChunk{CommandID: commandID, Data: data})
}

func (c *WsClient) SendStderr(commandID, data string) error {
	return c.sendMsg(MsgTypeStderrChunk, StderrChunk{CommandID: commandID, Data: data})
}

func (c *WsClient) SendResult(result ExecResult) error {
	return c.sendMsg(MsgTypeExecResult, result)
}

func (c *WsClient) SendHeartbeatResponse() error {
	return c.sendMsg(MsgTypeHeartbeatResponse, map[string]string{})
}

func (c *WsClient) sendMsg(msgType MessageType, data interface{}) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if !c.connected || c.conn == nil {
		return fmt.Errorf("not connected")
	}

	msg := Message{Type: msgType, Data: data}
	if err := c.conn.WriteJSON(msg); err != nil {
		c.connected = false
		return err
	}
	return nil
}

func (c *WsClient) handleDisconnect() {
	c.mu.Lock()
	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
	}
	c.connected = false
	c.mu.Unlock()
	logger.Warn("WebSocket disconnected")
}

func (c *WsClient) tryReconnect() {
	backoffs := []time.Duration{1, 2, 4, 8, 16, 30, 60}
	for i := 0; ; i++ {
		select {
		case <-c.done:
			return
		default:
		}
		idx := i
		if idx >= len(backoffs) {
			idx = len(backoffs) - 1
		}
		d := backoffs[idx]
		logger.Info("Reconnecting in %v...", d)
		time.Sleep(d * time.Second)
		err := c.Connect()
		if err == nil {
			logger.Info("Reconnected successfully")
			return
		}
		logger.Warn("Reconnect failed: %v", err)
		// 已耗尽初始回退序列后，每次等待 60s 再试
		if i >= len(backoffs)-1 {
			i = len(backoffs) - 2 // 下次循环使用 60s
		}
	}
}

func (c *WsClient) Close() {
	c.reconnect = false
	close(c.done)
	c.handleDisconnect()
}

func (c *WsClient) writeJSON(v interface{}) error {
	if c.conn == nil {
		return fmt.Errorf("not connected")
	}
	return c.conn.WriteJSON(v)
}

func (c *WsClient) IsConnected() bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.connected
}
