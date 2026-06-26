// Hello plugin — ExecutorPlugin 示例，演示 taskpps execute 协议。
//
//	type: executor
//	params: message (string)
//
// 在 pipeline YAML 中使用:
//   HelloPlugin:
//     message: "hello world"
//
// 编译: go build -o hello ./cmd/hello/
// 安装: cp hello <project>/official_plugins/hello/

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
	Hooks        []string         `json:"hooks,omitempty"`
	ParamsSchema map[string]Field `json:"params_schema"`
	ConfigSchema map[string]Field `json:"config_schema,omitempty"`
}

type Field struct {
	Type     string   `json:"type"`
	Required bool     `json:"required"`
	Label    string   `json:"label"`
	Default  string   `json:"default,omitempty"`
	Enum     []string `json:"enum,omitempty"`
}

type ExecuteResult struct {
	ExitCode int    `json:"exit_code"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	Duration float64 `json:"duration"`
}

var describe = DescribeResult{
	VerifyKey: getVerifyKey(),
	Name:      "hello",
	Type:      "executor",
	Version:   "1.0.0",
	HelpMsg:   "Hello Executor Plugin — 演示 taskpps ExecutorPlugin 协议\n\n在 pipeline 中使用:\n  HelloPlugin:\n    message: \"hello world\"\n    delay: 1   # 可选，模拟耗时操作(秒)",
	Hooks:     nil,
	ParamsSchema: map[string]Field{
		"message": {Type: "string", Required: true, Label: "输出消息"},
		"delay":   {Type: "integer", Required: false, Default: "0", Label: "模拟延迟(秒)"},
	},
	ConfigSchema: nil,
}

func main() {
	scanner := bufio.NewScanner(os.Stdin)
	writer := bufio.NewWriter(os.Stdout)
	config := make(map[string]interface{})

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

		case "on_load":
			if req.Params != nil {
				var p struct {
					Config map[string]interface{} `json:"config"`
				}
				if err := json.Unmarshal(req.Params, &p); err == nil && p.Config != nil {
					for k, v := range p.Config {
						config[k] = v
					}
				}
			}
			writeOK(writer, req.ID)

		case "execute":
			var params struct {
				Message string  `json:"message"`
				Delay   float64 `json:"delay"`
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
			if params.Delay > 0 {
				time.Sleep(time.Duration(params.Delay * float64(time.Second)))
			}
			elapsed := time.Since(start).Seconds()

			result := ExecuteResult{
				ExitCode: 0,
				Stdout:   params.Message,
				Stderr:   "",
				Duration: elapsed,
			}
			data, _ := json.Marshal(result)
			writeResult(writer, req.ID, data)

			fmt.Fprintf(os.Stderr, "hello: %s (%.2fs)\n", params.Message, elapsed)

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
