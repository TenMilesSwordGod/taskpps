package agent

import (
	"os"
	"os/signal"
	"syscall"

	"github.com/taskpps/execution-agent/logger"
)

type Agent struct {
	config   *AgentConfig
	wsClient *WsClient
	executor *Executor
	stopCh   chan struct{}
}

type AgentConfig struct {
	ServerURL string
	AgentID   string
	Secret    string
	Shell     string
}

func NewAgent(config *AgentConfig) *Agent {
	a := &Agent{
		config: config,
		stopCh: make(chan struct{}),
	}

	hostname, _ := os.Hostname()
	a.wsClient = NewWsClient(config.ServerURL, config.AgentID, config.Secret, hostname, os.Getpid())
	a.executor = NewExecutor(
		config.Shell,
		a.onStdout,
		a.onStderr,
		a.onResult,
	)

	a.wsClient.OnCommand = func(cmd ExecCommand) {
		a.executor.Execute(cmd)
	}
	a.wsClient.OnCancel = func(commandID string) {
		a.executor.Cancel(commandID)
	}

	return a
}

func (a *Agent) Start() error {
	if err := a.wsClient.Connect(); err != nil {
		return err
	}
	a.wsClient.Run()

	hostname, _ := os.Hostname()
	logger.Info("Agent started: id=%s host=%s pid=%d", a.config.AgentID, hostname, os.Getpid())

	a.handleSignals()
	return nil
}

func (a *Agent) Stop() {
	logger.Info("Agent stopping...")
	a.executor.CancelAll()
	a.wsClient.Close()
	close(a.stopCh)
	logger.Info("Agent stopped")
}

func (a *Agent) Wait() {
	<-a.stopCh
}

func (a *Agent) onStdout(commandID, data string) {
	if err := a.wsClient.SendStdout(commandID, data); err != nil {
		logger.Debug("SendStdout error: %v", err)
	}
}

func (a *Agent) onStderr(commandID, data string) {
	if err := a.wsClient.SendStderr(commandID, data); err != nil {
		logger.Debug("SendStderr error: %v", err)
	}
}

func (a *Agent) onResult(result ExecResult) {
	logger.Info("Command %s finished: exit_code=%d signal=%s duration=%dms",
		result.CommandID, result.ExitCode, result.SignalName, result.DurationMs)
	if err := a.wsClient.SendResult(result); err != nil {
		logger.Error("SendResult error: %v", err)
	}
}

func (a *Agent) handleSignals() {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		select {
		case sig := <-sigCh:
			logger.Info("Received signal %v, shutting down...", sig)
			a.Stop()
		case <-a.stopCh:
		}
		signal.Stop(sigCh)
	}()
}
