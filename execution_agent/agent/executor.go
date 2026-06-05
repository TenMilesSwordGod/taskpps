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

type runningCmd struct {
	Cmd       *exec.Cmd
	CommandID string
	Cancel    context.CancelFunc
	StartTime time.Time
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
		shell:       shell,
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

	rc := &runningCmd{Cmd: cmd, CommandID: req.CommandID, Cancel: cancel, StartTime: startTime}
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
	if !exists || rc.Cmd == nil {
		return
	}

	logger.Info("Cancelling command %s (PID=%d)", commandID, rc.Cmd.Process.Pid)

	killProcessTree(rc.Cmd.Process.Pid, syscall.SIGTERM)

	done := make(chan struct{})
	go func() {
		rc.Cmd.Wait()
		close(done)
	}()

	select {
	case <-done:
		logger.Info("Command %s terminated after SIGTERM", commandID)
	case <-time.After(5 * time.Second):
		logger.Warn("Command %s did not respond to SIGTERM, sending SIGKILL", commandID)
		killProcessTree(rc.Cmd.Process.Pid, syscall.SIGKILL)
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
