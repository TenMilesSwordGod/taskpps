package agent

type MessageType string

const (
	MsgTypeHandshakeRequest  MessageType = "handshake_request"
	MsgTypeHandshakeResponse MessageType = "handshake_response"
	MsgTypeExecCommand       MessageType = "exec_command"
	MsgTypeCancelCommand     MessageType = "cancel_command"
	MsgTypeStdoutChunk       MessageType = "stdout_chunk"
	MsgTypeStderrChunk       MessageType = "stderr_chunk"
	MsgTypeExecResult        MessageType = "exec_result"
	MsgTypeCompleteRequest   MessageType = "complete_request"
	MsgTypeCompleteResult    MessageType = "complete_result"
	MsgTypePing              MessageType = "ping"
	MsgTypeHeartbeatRequest  MessageType = "heartbeat_request"
	MsgTypeHeartbeatResponse MessageType = "heartbeat_response"
)

type Message struct {
	Type MessageType `json:"type"`
	Data interface{} `json:"data"`
}

type HandshakeRequest struct {
	AgentID  string `json:"agent_id"`
	Secret   string `json:"secret"`
	Version  string `json:"version"`
	Hostname string `json:"hostname"`
	AgentPID int    `json:"agent_pid"`
	OS       string `json:"os"`
	Arch     string `json:"arch"`
}

type HandshakeResponse struct {
	AgentID      string `json:"agent_id"`
	Hostname     string `json:"hostname"`
	AgentVersion string `json:"agent_version"`
	AgentPID     int    `json:"agent_pid"`
}

type ExecCommand struct {
	CommandID string            `json:"command_id"`
	Command   string            `json:"command"`
	Env       map[string]string `json:"env"`
	Cwd       string            `json:"cwd"`
	Timeout   int               `json:"timeout"`
}

type CancelCommand struct {
	CommandID string `json:"command_id"`
}

type StdoutChunk struct {
	CommandID string `json:"command_id"`
	Data      string `json:"data"`
}

type StderrChunk struct {
	CommandID string `json:"command_id"`
	Data      string `json:"data"`
}

type ExecResult struct {
	CommandID  string `json:"command_id"`
	ExitCode   int    `json:"exit_code"`
	SignalName string `json:"signal_name,omitempty"`
	DurationMs int64  `json:"duration_ms"`
	Error      string `json:"error,omitempty"`
}

type CompleteRequest struct {
	RequestID string `json:"request_id"`
	// Line 是当前输入整行（含光标前的全部字符）
	Line   string `json:"line"`
	Cursor int    `json:"cursor"`
	Cwd    string `json:"cwd"`
}

type CompleteResult struct {
	RequestID string `json:"request_id"`
	// Prefix 是被补全的原始 token（agent 端解析，保证与候选匹配）
	Prefix     string   `json:"prefix"`
	Candidates []string `json:"candidates"`
	Error      string   `json:"error,omitempty"`
}

const ProtocolVersion = "1.0.0"
