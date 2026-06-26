// Echo plugin — 最小 ExecutorPlugin 示例，演示 taskpps PluginCenter 协议。
//
//	type: executor
//
// 在 pipeline YAML 中使用:
//   EchoPlugin:
//     message: "hello world"
//
// 编译: go build -o echo ./cmd/echo/
// 安装: cp echo <project>/official_plugins/echo/
// 测试: echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./echo

package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"time"
)

func getVerifyKey() string {
	return os.Getenv("TASKPPS_VERIFY_KEY")
}

type Request struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	ID      int             `json:"id"`
}

type Response struct {
	JSONRPC string          `json:"jsonrpc"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *RPCError       `json:"error,omitempty"`
	ID      int             `json:"id"`
}

type RPCError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type DescribeResult struct {
	VerifyKey    string           `json:"verify_key"`
	Name         string           `json:"name"`
	Type         string           `json:"type"`
	Version      string           `json:"version"`
	HelpMsg      string           `json:"help_msg"`
	ParamsSchema map[string]Field `json:"params_schema"`
}

type Field struct {
	Type     string   `json:"type"`
	Required bool     `json:"required"`
	Label    string   `json:"label"`
	Default  string   `json:"default,omitempty"`
	Enum     []string `json:"enum,omitempty"`
}

type ExecuteResult struct {
	ExitCode int     `json:"exit_code"`
	Stdout   string  `json:"stdout"`
	Stderr   string  `json:"stderr"`
	Duration float64 `json:"duration"`
}

var describe = DescribeResult{
	VerifyKey: getVerifyKey(),
	Name:      "echo",
	Type:      "executor",
	Version:   "1.0.0",
	HelpMsg:   "Echo 执行器 — 最小 ExecutorPlugin 示例\n\n在 pipeline 中使用:\n  EchoPlugin:\n    message: \"hello world\"\n\n参数:\n  message (必填) — 要输出的消息",
	ParamsSchema: map[string]Field{
		"message": {Type: "string", Required: true, Label: "输出消息"},
	},
}

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	writer := bufio.NewWriter(os.Stdout)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var req Request
		if err := json.Unmarshal(line, &req); err != nil {
			writeError(writer, req.ID, -32700, "parse error: "+err.Error())
			continue
		}

		switch req.Method {
		case "describe":
			data, _ := json.Marshal(describe)
			writeResult(writer, req.ID, data)

		case "execute":
			var params struct {
				Message string `json:"message"`
			}
			if err := json.Unmarshal(req.Params, &params); err != nil {
				writeError(writer, req.ID, -32602, "invalid params: "+err.Error())
				continue
			}
			if params.Message == "" {
				writeError(writer, req.ID, -32602, "message is required")
				continue
			}

			start := time.Now()
			elapsed := time.Since(start).Seconds()

			result := ExecuteResult{
				ExitCode: 0,
				Stdout:   params.Message,
				Stderr:   "",
				Duration: elapsed,
			}
			data, _ := json.Marshal(result)
			writeResult(writer, req.ID, data)

			fmt.Fprintf(os.Stderr, "echo: %s (%.4fs)\n", params.Message, elapsed)

		case "on_shutdown":
			writeOK(writer, req.ID)
			os.Exit(0)

		default:
			writeError(writer, req.ID, -32601, "method not found: "+req.Method)
		}
	}
}

func writeResult(w *bufio.Writer, id int, result json.RawMessage) {
	resp := Response{JSONRPC: "2.0", Result: result, ID: id}
	data, _ := json.Marshal(resp)
	fmt.Fprintln(w, string(data))
	w.Flush()
}

func writeOK(w *bufio.Writer, id int) {
	writeResult(w, id, json.RawMessage(`{"status":"ok"}`))
}

func writeError(w *bufio.Writer, id int, code int, msg string) {
	resp := Response{JSONRPC: "2.0", Error: &RPCError{Code: code, Message: msg}, ID: id}
	data, _ := json.Marshal(resp)
	fmt.Fprintln(w, string(data))
	w.Flush()
}
