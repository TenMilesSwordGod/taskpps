package agent

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/taskpps/execution-agent/logger"
)

// completer.go — Web REPL 的 Tab 补全实现。
//
// 补全在 agent 端执行（bash compgen），返回的是 agent 真实环境的结果，
// 服务端/前端不做任何兜底模拟。prefix 通过环境变量传入脚本，
// 避免把用户输入拼进 shell 脚本导致注入或引号破坏。

// CompleteTimeout 是补全命令的执行超时；补全是交互辅助，不能拖慢输入。
const CompleteTimeout = 3 * time.Second

// Complete 解析请求中的当前 token，调用 bash compgen 返回候选。
//
// 为什么在 agent 端解析 token 而不是服务端：光标位置与引号状态只与
// agent 的 shell 语义相关，且 agent 端解析结果（prefix）与候选同源，
// 前端可直接用 prefix 定位替换范围，避免两端 tokenize 规则不一致。
func (e *Executor) Complete(req CompleteRequest) CompleteResult {
	result := CompleteResult{RequestID: req.RequestID}

	token, _, isCommandPos := parseToken(req.Line, req.Cursor)
	result.Prefix = token

	// 空 token（如 "ls " 后按 Tab）不补全：全量命令/文件列表对交互没有价值
	if token == "" {
		return result
	}

	script, err := buildCompleteScript(token, isCommandPos, firstWord(req.Line))
	if err != nil {
		result.Error = err.Error()
		return result
	}

	ctx, cancel := context.WithTimeout(context.Background(), CompleteTimeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, e.shell, "-c", script)
	// cwd 解析与 Execute 一致：请求优先，其次 agent 默认工作目录。
	// 同一变量同时用于 compgen 的执行目录与候选目录类型判定。
	dir := req.Cwd
	if dir == "" {
		dir = e.defaultDir
	}
	cmd.Dir = dir
	// prefix 以环境变量传入：脚本内用双引号引用，特殊字符不会破坏脚本结构
	cmd.Env = append(os.Environ(), "TASKPPS_COMP_PREFIX="+token)

	// 丢弃 stderr：compgen 的错误信息对用户无价值，错误通过 Error 字段体现
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			result.Error = "completion timeout"
		} else {
			logger.Warn("Completion failed for %q: %v", token, err)
			result.Error = fmt.Sprintf("completion failed: %v", err)
		}
		return result
	}

	for _, line := range strings.Split(string(out), "\n") {
		if line == "" {
			continue
		}
		result.Candidates = append(result.Candidates, markDirs(dir, line))
	}
	return result
}

// markDirs 为目录候选追加 /（bash 裸 compgen -f/-d 输出的目录不带后缀，
// 与终端 tab 补全的显示习惯不一致，这里补齐以便前端区分目录与文件）。
func markDirs(cwd, candidate string) string {
	if strings.HasSuffix(candidate, "/") {
		return candidate
	}
	path := candidate
	if !filepath.IsAbs(path) && cwd != "" {
		path = filepath.Join(cwd, path)
	}
	if info, err := os.Stat(path); err == nil && info.IsDir() {
		return candidate + "/"
	}
	return candidate
}

// parseToken 解析 line[:cursor] 中的最后一个词作为补全 token。
//
// 必须从前往后扫描并跟踪引号状态：从后往前配对引号无法识别"未闭合引号"
// （如 cd "./my d 中空格实际在引号内，不是 token 分隔符）。
func parseToken(line string, cursor int) (token string, tokenStart int, isCommandPos bool) {
	if cursor < 0 || cursor > len(line) {
		cursor = len(line)
	}
	head := line[:cursor]

	// 记录最后一个引号外空白的位置，即 token 起点
	var quote byte
	lastBreak := -1
	for i := 0; i < len(head); i++ {
		c := head[i]
		if c == '\\' {
			// 转义字符后的字符不参与判断（如 my\ dir 的空格不是分隔符）
			i++
			continue
		}
		if quote != 0 {
			if c == quote {
				quote = 0
			}
			continue
		}
		if c == '\'' || c == '"' {
			quote = c
			continue
		}
		if c == ' ' || c == '\t' {
			lastBreak = i
		}
	}
	tokenStart = lastBreak + 1
	raw := head[tokenStart:cursor]

	// 剥掉包裹整个 token 的引号对（如 cd "./my d 中未闭合的 "）
	token = raw
	if len(token) >= 2 && ((token[0] == '"' && token[len(token)-1] == '"') || (token[0] == '\'' && token[len(token)-1] == '\'')) {
		token = token[1 : len(token)-1]
	} else if len(token) >= 1 && (token[0] == '"' || token[0] == '\'') {
		token = token[1:]
	}

	before := strings.TrimRight(head[:tokenStart], " \t")
	isCommandPos = before == ""
	return token, tokenStart, isCommandPos
}

// firstWord 返回行首命令名（用于 cd 只补目录等场景）。
func firstWord(line string) string {
	fields := strings.Fields(line)
	if len(fields) == 0 {
		return ""
	}
	return fields[0]
}

// buildCompleteScript 根据 token 位置构造 compgen 脚本。
//
// compgen -f 对目录自动追加 /，compgen -d 只列目录（cd 场景），
// compgen -c 列可执行命令。命令位置若 token 是路径前缀则补路径，
// 否则先补命令、无结果再补文件（与 bash 行为一致）。
func buildCompleteScript(token string, isCommandPos bool, cmdName string) (string, error) {
	if isCommandPos {
		if strings.HasPrefix(token, "/") || strings.HasPrefix(token, "./") || strings.HasPrefix(token, "../") {
			return `compgen -f -- "$TASKPPS_COMP_PREFIX"`, nil
		}
		// 命令补全无结果时回退到文件补全（bash 行为：PATH 未命中则提示当前目录文件）
		return `out=$(compgen -c -- "$TASKPPS_COMP_PREFIX"); if [ -z "$out" ]; then compgen -f -- "$TASKPPS_COMP_PREFIX"; else printf '%s\n' "$out"; fi`, nil
	}
	if cmdName == "cd" {
		return `compgen -d -- "$TASKPPS_COMP_PREFIX"`, nil
	}
	return `compgen -f -- "$TASKPPS_COMP_PREFIX"`, nil
}
