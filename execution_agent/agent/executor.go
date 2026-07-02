package agent

import (
	"context"
	"fmt"
	"os/exec"
	"sync"
	"syscall"
	"time"

	"github.com/taskpps/execution-agent/logger"
)

/** Shell 探测的备选列表。优先级：bash > dash > sh。 */
var shellFallbacks = []string{
	"/bin/bash",
	"/usr/bin/bash",
	"/bin/dash",
	"/usr/bin/dash",
	"/bin/sh",
	"/usr/bin/sh",
}

/**
 * resolveShell 在配置的 shell 不可用时按 fallback 列表自动降级。
 *
 * 直接以 -c 调用未知的 shell 会得到 "fork/exec ...: no such file or directory"
 * (issue #56) 或 "fork/exec ...: permission denied" 这种非常笼统的错误，
 * 用户很难定位是环境缺少 bash 还是路径写错。
 * 降级到存在的 shell 后再启动命令，至少能让流水线继续跑起来。
 */
func resolveShell(configured string) string {
	if configured == "" || isExecutable(configured) {
		return configured
	}
	logger.Warn("Shell %q 不可用，按 fallback 列表自动选择", configured)
	for _, candidate := range shellFallbacks {
		if candidate == configured {
			continue
		}
		if isExecutable(candidate) {
			logger.Warn("使用 fallback shell: %s", candidate)
			return candidate
		}
	}
	logger.Warn("所有 fallback shell 都不存在，将保留原配置 %q 让其失败以便定位", configured)
	return configured
}

// isExecutable 检查路径是否可实际执行。
// 除了 LookPath 解析外，还尝试实际运行来验证动态链接器等依赖可用（issue #171）。
func isExecutable(path string) bool {
	if path == "" {
		return false
	}
	resolved, err := exec.LookPath(path)
	if err != nil {
		return false
	}
	if resolved == "" {
		return false
	}
	// 尝试实际执行，验证动态链接器等运行时依赖存在
	cmd := exec.Command(path, "-c", "exit 0")
	return cmd.Run() == nil
}

type runningCmd struct {
	Cmd       *exec.Cmd
	CommandID string
	Cancel    context.CancelFunc
	StartTime time.Time
	// Exited is closed by waitForCompletion after Wait() returns.
	// Cancel() selects on this instead of calling Wait() a second time
	// (which would return immediately with "Wait was already called").
	Exited chan struct{}
}

type Executor struct {
	mu          sync.Mutex
	runningCmds map[string]*runningCmd
	shell       string
	defaultDir  string
	onStdout    func(commandID, data string)
	onStderr    func(commandID, data string)
	onResult    func(result ExecResult)
}

func NewExecutor(shell string, defaultDir string, onStdout, onStderr func(string, string), onResult func(ExecResult)) *Executor {
	if shell == "" {
		shell = "/bin/bash"
	}
	return &Executor{
		runningCmds: make(map[string]*runningCmd),
		shell:       resolveShell(shell),
		defaultDir:  defaultDir,
		onStdout:    onStdout,
		onStderr:    onStderr,
		onResult:    onResult,
	}
}

func (e *Executor) Execute(req ExecCommand) {
	e.mu.Lock()
	if _, exists := e.runningCmds[req.CommandID]; exists {
		e.mu.Unlock()
		logger.Warn("Command %s is already running", req.CommandID)
		return
	}
	e.mu.Unlock()

	var ctx context.Context
	var cancel context.CancelFunc
	if req.Timeout > 0 {
		ctx, cancel = context.WithTimeout(context.Background(), time.Duration(req.Timeout)*time.Second)
	} else {
		ctx, cancel = context.WithCancel(context.Background())
	}

	cmd := exec.CommandContext(ctx, e.shell, "-c", req.Command)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if req.Cwd != "" {
		cmd.Dir = req.Cwd
	} else if e.defaultDir != "" {
		cmd.Dir = e.defaultDir
	}
	if req.Env != nil {
		cmd.Env = mergeEnv(osEnviron(), req.Env)
	}

	stdoutPipe, err := cmd.StdoutPipe()
	if err != nil {
		cancel()
		e.sendResult(ExecResult{CommandID: req.CommandID, ExitCode: -1, Error: fmt.Sprintf("stdout pipe: %v", err)})
		return
	}
	stderrPipe, err := cmd.StderrPipe()
	if err != nil {
		cancel()
		e.sendResult(ExecResult{CommandID: req.CommandID, ExitCode: -1, Error: fmt.Sprintf("stderr pipe: %v", err)})
		return
	}

	startTime := time.Now()
	if err := cmd.Start(); err != nil {
		cancel()
		e.sendResult(ExecResult{CommandID: req.CommandID, ExitCode: -1, Error: fmt.Sprintf("start: %v", err), DurationMs: time.Since(startTime).Milliseconds()})
		return
	}

	rc := &runningCmd{Cmd: cmd, CommandID: req.CommandID, Cancel: cancel, StartTime: startTime, Exited: make(chan struct{})}
	e.mu.Lock()
	e.runningCmds[req.CommandID] = rc
	e.mu.Unlock()

	go e.streamOutput(req.CommandID, stdoutPipe, e.onStdout)
	go e.streamOutput(req.CommandID, stderrPipe, e.onStderr)

	go e.waitForCompletion(rc)
}

func (e *Executor) Cancel(commandID string) {
	e.mu.Lock()
	rc, exists := e.runningCmds[commandID]
	e.mu.Unlock()
	if !exists || rc.Cmd == nil || rc.Cmd.Process == nil {
		return
	}

	pid := rc.Cmd.Process.Pid
	logger.Info("Cancelling command %s (PID=%d)", commandID, pid)

	// Send SIGTERM to the entire process group (bash + all children).
	// The command is launched with Setpgid=true so the process is the
	// leader of its own pgid, and a negative PID in kill(2) targets the
	// whole group. This is essential: bash ignores SIGTERM while waiting
	// for its foreground child, so signalling only the parent would leak
	// orphans (e.g. "sleep 15" surviving after bash is killed).
	//
	// Fall back to the per-PID tree walk if Getpgid ever fails.
	pgid, err := syscall.Getpgid(pid)
	if err == nil && pgid == pid {
		_ = syscall.Kill(-pgid, syscall.SIGTERM)
	} else {
		killProcessTree(pid, syscall.SIGTERM)
	}

	// waitForCompletion has already called Wait(); a second Wait() would
	// return immediately ("Wait was already called"), which would make
	// the select fire instantly and skip the SIGKILL fallback. Use the
	// Exited channel that waitForCompletion closes after Wait() returns.
	select {
	case <-rc.Exited:
		logger.Info("Command %s terminated after SIGTERM", commandID)
	case <-time.After(5 * time.Second):
		logger.Warn("Command %s did not respond to SIGTERM, sending SIGKILL", commandID)
		if err == nil && pgid == pid {
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		} else {
			killProcessTree(pid, syscall.SIGKILL)
		}
		<-rc.Exited
	}

	rc.Cancel()
}

func (e *Executor) CancelAll() {
	e.mu.Lock()
	ids := make([]string, 0, len(e.runningCmds))
	for id := range e.runningCmds {
		ids = append(ids, id)
	}
	e.mu.Unlock()
	for _, id := range ids {
		e.Cancel(id)
	}
}

func (e *Executor) waitForCompletion(rc *runningCmd) {
	err := rc.Cmd.Wait()
	close(rc.Exited)
	duration := time.Since(rc.StartTime).Milliseconds()

	result := ExecResult{CommandID: rc.CommandID, DurationMs: duration}

	if err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok {
			ws := exitErr.Sys().(syscall.WaitStatus)
			if ws.Signaled() {
				result.ExitCode = -int(ws.Signal())
				result.SignalName = signalToString(ws.Signal())
				if rc.Cmd.ProcessState != nil && rc.Cmd.ProcessState.ExitCode() == -1 && result.SignalName == "" {
					result.SignalName = "SIGKILL"
				}
			} else {
				result.ExitCode = ws.ExitStatus()
			}
		} else {
			result.ExitCode = -1
			result.Error = err.Error()
		}
	} else {
		result.ExitCode = 0
	}

	if rc.Cmd.ProcessState != nil && rc.Cmd.ProcessState.ExitCode() >= 0 && result.ExitCode < 0 {
		result.ExitCode = rc.Cmd.ProcessState.ExitCode()
	}

	e.mu.Lock()
	delete(e.runningCmds, rc.CommandID)
	e.mu.Unlock()

	e.sendResult(result)
}

func (e *Executor) sendResult(result ExecResult) {
	if e.onResult != nil {
		e.onResult(result)
	}
}

func (e *Executor) streamOutput(commandID string, pipe ioReader, callback func(string, string)) {
	if callback == nil {
		return
	}
	ch := readPipeBinary(pipe)
	for data := range ch {
		callback(commandID, string(data))
	}
}

type ioReader interface {
	Read([]byte) (int, error)
}

func osEnviron() []string {
	return syscall.Environ()
}

func mergeEnv(base []string, extra map[string]string) []string {
	merged := make([]string, len(base))
	copy(merged, base)
	for k, v := range extra {
		merged = append(merged, k+"="+v)
	}
	return merged
}
