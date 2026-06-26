// Git plugin — ExecutorPlugin，支持 git clone/checkout/pull 操作。
//
//	type: executor
//	params: remote (string, required), branch (string, required), action (enum: clone/checkout/pull, required)
//
// 在 pipeline YAML 中使用:
//   plugin: git_plugin
//   params:
//     remote: "https://github.com/user/repo.git"
//     branch: "main"
//     action: "clone"
//
// host 继承自 task/subpipeline/pipeline config，不设则本地执行。
//
// 编译: go build -o git ./cmd/git/
// 安装: cp git <project>/official_plugins/git/
// 测试: echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./git

package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
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
	ExitCode int     `json:"exit_code"`
	Stdout   string  `json:"stdout"`
	Stderr   string  `json:"stderr"`
	Duration float64 `json:"duration"`
}

var describe = DescribeResult{
	VerifyKey: getVerifyKey(),
	Name:      "git_plugin",
	Type:      "executor",
	Version:   "1.0.0",
	HelpMsg:   "Git 执行器 — 支持 clone/checkout/pull 操作\n\n在 pipeline 中使用:\n  plugin: git_plugin\n  params:\n    remote: \"https://github.com/user/repo.git\"\n    branch: \"main\"\n    action: \"clone\"\n\nhost 继承自 task/subpipeline/pipeline config，不设则本地执行。",
	Hooks:     nil,
	ParamsSchema: map[string]Field{
		"remote": {Type: "string", Required: true, Label: "远程仓库地址"},
		"branch": {Type: "string", Required: true, Label: "分支名"},
		"action": {Type: "string", Required: true, Label: "操作", Enum: []string{"clone", "checkout", "pull"}},
	},
	ConfigSchema: nil,
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
				Remote string `json:"remote"`
				Branch string `json:"branch"`
				Action string `json:"action"`
			}
			if err := json.Unmarshal(req.Params, &params); err != nil {
				writeError(writer, req.ID, -32602, "invalid params: "+err.Error())
				continue
			}
			if params.Remote == "" {
				writeError(writer, req.ID, -32602, "remote is required")
				continue
			}
			if params.Branch == "" {
				writeError(writer, req.ID, -32602, "branch is required")
				continue
			}
			validActions := map[string]bool{"clone": true, "checkout": true, "pull": true}
			if !validActions[params.Action] {
				writeError(writer, req.ID, -32602, "action must be one of: clone, checkout, pull")
				continue
			}

			start := time.Now()

			var cmd *exec.Cmd
			switch params.Action {
			case "clone":
				cmd = exec.Command("git", "clone", "--branch", params.Branch, params.Remote)
			case "checkout":
				cmd = exec.Command("git", "checkout", params.Branch)
			case "pull":
				cmd = exec.Command("git", "pull", "origin", params.Branch)
			}

			stdout, err := cmd.Output()
			elapsed := time.Since(start).Seconds()

			var exitCode int
			var stderr string
			var stdoutStr string

			if err != nil {
				if exitErr, ok := err.(*exec.ExitError); ok {
					exitCode = exitErr.ExitCode()
					stderr = string(exitErr.Stderr)
					stdoutStr = string(stdout)
				} else {
					exitCode = -1
					stderr = err.Error()
				}
			} else {
				exitCode = 0
				stdoutStr = string(stdout)
			}

			result := ExecuteResult{
				ExitCode: exitCode,
				Stdout:   stdoutStr,
				Stderr:   stderr,
				Duration: elapsed,
			}
			data, _ := json.Marshal(result)
			writeResult(writer, req.ID, data)

			fmt.Fprintf(os.Stderr, "git_plugin: %s %s (branch=%s) exit=%d (%.2fs)\n",
				params.Action, params.Remote, params.Branch, exitCode, elapsed)

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
