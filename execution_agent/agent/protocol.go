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

const ProtocolVersion = "1.0.0"
