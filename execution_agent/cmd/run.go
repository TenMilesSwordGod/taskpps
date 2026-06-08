package cmd

import (
	"fmt"
	"os"
	"strconv"
	"syscall"

	"github.com/spf13/cobra"
	"github.com/taskpps/execution-agent/agent"
	"github.com/taskpps/execution-agent/config"
	"github.com/taskpps/execution-agent/logger"
)

var (
	serverURL string
	agentID   string
	secret    string
	shell     string
	pidFile   string
	logFile   string
	workDir   string
	daemon    bool
)

var runCmd = &cobra.Command{
	Use:   "run",
	Short: "启动 taskpps-agent",
	Long:  "启动 taskpps-agent，连接到 taskpps server 执行远程命令",
	RunE: func(cmd *cobra.Command, args []string) error {
		if daemon {
			return runDaemon()
		}
		return runForeground()
	},
}

func init() {
	runCmd.Flags().StringVar(&serverURL, "server", "ws://localhost:26521/api/ws/agent", "taskpps server WebSocket URL")
	runCmd.Flags().StringVar(&agentID, "agent-id", "", "Agent ID (默认为主机名)")
	runCmd.Flags().StringVar(&secret, "secret", "", "预共享密钥")
	runCmd.Flags().StringVar(&shell, "shell", "/bin/bash", "Shell 路径")
	runCmd.Flags().StringVar(&workDir, "work-dir", "", "默认工作目录(执行命令时的 cwd)")
	runCmd.Flags().StringVar(&pidFile, "pid-file", "/var/run/taskpps-agent.pid", "PID 文件路径")
	runCmd.Flags().StringVar(&logFile, "log-file", "", "日志文件路径")
	runCmd.Flags().BoolVar(&daemon, "daemon", false, "以 daemon 模式运行")

	RootCmd.AddCommand(runCmd)
}

func runForeground() error {
	if agentID == "" {
		hostname, _ := os.Hostname()
		agentID = hostname
	}
	if pidFile == "" {
		pidFile = "/var/run/taskpps-agent.pid"
	}

	// Refuse to start if a daemon is already recorded as running. A second
	// agent with the same agent_id would race the daemon for handshake
	// ownership on the server. See issue #14.
	if running, pid, err := checkInstanceRunning(pidFile); err != nil {
		return err
	} else if running {
		return fmt.Errorf("taskpps-agent 已经有一个实例在运行 (PID: %d, PID 文件: %s); 先 stop 再 start", pid, pidFile)
	}

	if err := logger.Init(logFile); err != nil {
		return fmt.Errorf("初始化日志失败: %w", err)
	}
	defer logger.Close()

	logger.Info("taskpps-agent starting (foreground)")
	logger.Info("  Server: %s", serverURL)
	logger.Info("  Agent ID: %s", agentID)

	agentConfig := &agent.AgentConfig{
		ServerURL: serverURL,
		AgentID:   agentID,
		Secret:    secret,
		Shell:     shell,
		WorkDir:   workDir,
	}

	a := agent.NewAgent(agentConfig)
	if err := a.Start(); err != nil {
		logger.Error("Agent 启动失败: %v", err)
		return err
	}

	a.Wait()
	return nil
}

func runDaemon() error {
	if agentID == "" {
		hostname, _ := os.Hostname()
		agentID = hostname
	}

	if logFile == "" {
		logFile = "/var/log/taskpps-agent.log"
	}
	if pidFile == "" {
		pidFile = "/var/run/taskpps-agent.pid"
	}

	// Refuse to start a second daemon. The previous implementation would
	// blindly overwrite the PID file with the new process's PID, leaving
	// the old daemon running and making `status` and `stop` point at the
	// wrong process. See issue #14.
	if running, pid, err := checkInstanceRunning(pidFile); err != nil {
		return err
	} else if running {
		return fmt.Errorf("taskpps-agent daemon 已经在运行 (PID: %d, PID 文件: %s); 先 stop 再 start", pid, pidFile)
	}

	args := os.Args
	for i, arg := range args {
		if arg == "--daemon" {
			args = append(args[:i], args[i+1:]...)
			break
		}
	}

	attr := &os.ProcAttr{
		Dir: ".",
		Env: os.Environ(),
		Files: []*os.File{
			os.Stdin,
			nil,
			nil,
		},
		Sys: &syscall.SysProcAttr{Setsid: true},
	}

	f, err := os.OpenFile(logFile, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err == nil {
		attr.Files[1] = f
		attr.Files[2] = f
		defer f.Close()
	}

	process, err := os.StartProcess(args[0], args, attr)
	if err != nil {
		return fmt.Errorf("daemon 启动失败: %w", err)
	}

	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(process.Pid)+"\n"), 0644); err != nil {
		return fmt.Errorf("写入 PID 文件失败: %w", err)
	}

	fmt.Printf("taskpps-agent daemon 已启动 (PID: %d)\n", process.Pid)
	fmt.Printf("  PID 文件: %s\n", pidFile)
	fmt.Printf("  日志文件: %s\n", logFile)

	process.Release()
	return nil
}

func buildConfig() *config.Config {
	cfg := config.DefaultConfig()
	if serverURL != "" {
		cfg.ServerURL = serverURL
	}
	if agentID != "" {
		cfg.AgentID = agentID
	}
	if secret != "" {
		cfg.Secret = secret
	}
	if shell != "" {
		cfg.Shell = shell
	}
	if workDir != "" {
		cfg.WorkDir = workDir
	}
	if pidFile != "" {
		cfg.PidFile = pidFile
	}
	if logFile != "" {
		cfg.LogFile = logFile
	}
	cfg.Daemon = daemon
	return cfg
}
