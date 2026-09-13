package cmd

import (
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/taskpps/execution-agent/config"
)

// saveFlagVars 保存/恢复 buildConfig 与 run 命令依赖的包级 flag 变量，
// 避免用例之间互相污染（这些变量由 cobra flag 绑定，测试只能通过全局赋值驱动）。
func saveFlagVars(t *testing.T) {
	t.Helper()
	origServerURL, origAgentID, origSecret := serverURL, agentID, secret
	origShell, origPidFile, origLogFile := shell, pidFile, logFile
	origWorkDir, origDaemon := workDir, daemon
	t.Cleanup(func() {
		serverURL, agentID, secret = origServerURL, origAgentID, origSecret
		shell, pidFile, logFile = origShell, origPidFile, origLogFile
		workDir, daemon = origWorkDir, origDaemon
	})
}

// TestBuildConfig_OverridesDefaults 验证 flag 值正确覆盖 DefaultConfig 的字段。
func TestBuildConfig_OverridesDefaults(t *testing.T) {
	saveFlagVars(t)

	serverURL = "ws://custom:9999/api/ws/agent"
	agentID = "custom-agent"
	secret = "secret123"
	shell = "/bin/sh"
	workDir = "/custom/workdir"
	pidFile = "/custom/pid"
	logFile = "/custom/log"
	daemon = true

	cfg := buildConfig()
	checks := []struct {
		name string
		got  string
		want string
	}{
		{"ServerURL", cfg.ServerURL, serverURL},
		{"AgentID", cfg.AgentID, agentID},
		{"Secret", cfg.Secret, secret},
		{"Shell", cfg.Shell, shell},
		{"WorkDir", cfg.WorkDir, workDir},
		{"PidFile", cfg.PidFile, pidFile},
		{"LogFile", cfg.LogFile, logFile},
	}
	for _, c := range checks {
		if c.got != c.want {
			t.Errorf("buildConfig().%s = %q, want %q", c.name, c.got, c.want)
		}
	}
	if !cfg.Daemon {
		t.Error("buildConfig().Daemon = false, want true")
	}
}

// TestBuildConfig_KeepsDefaultsWhenEmpty 验证未传 flag 时保留默认配置，
// 防止 buildConfig 把空字符串写进配置。
func TestBuildConfig_KeepsDefaultsWhenEmpty(t *testing.T) {
	saveFlagVars(t)

	serverURL, agentID, secret = "", "", ""
	shell, workDir, pidFile, logFile = "", "", "", ""
	daemon = false

	cfg := buildConfig()
	def := config.DefaultConfig()
	if cfg.ServerURL != def.ServerURL || cfg.AgentID != def.AgentID || cfg.Shell != def.Shell {
		t.Errorf("empty flags should keep defaults, got %+v, want %+v", cfg, def)
	}
	if cfg.PidFile != def.PidFile || cfg.LogFile != def.LogFile || cfg.WorkDir != def.WorkDir || cfg.Secret != def.Secret {
		t.Errorf("empty flags should keep defaults, got %+v, want %+v", cfg, def)
	}
	if cfg.Daemon {
		t.Error("buildConfig().Daemon = true, want false")
	}
}

// TestRunForeground_RefusesWhenInstanceRunning 覆盖用户可见的"已有实例运行"提示：
// 已有存活进程占用 PID 文件时，run --daemon 之外的启动路径必须立即拒绝。
func TestRunForeground_RefusesWhenInstanceRunning(t *testing.T) {
	saveFlagVars(t)

	child := exec.Command("sleep", "30")
	if err := child.Start(); err != nil {
		t.Fatalf("启动子进程失败: %v", err)
	}
	t.Cleanup(func() {
		if child.ProcessState == nil {
			_ = child.Process.Kill()
			_, _ = child.Process.Wait()
		}
	})

	pidFile = filepath.Join(t.TempDir(), "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(child.Process.Pid)+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	err := runForeground()
	if err == nil {
		t.Fatal("expected runForeground to refuse when an instance is running")
	}
	if !strings.Contains(err.Error(), "已经有一个实例在运行") {
		t.Errorf("error = %v, want '已经有一个实例在运行'", err)
	}
}

// TestRunDaemon_RefusesWhenInstanceRunning 覆盖 daemon 模式的重复启动拒绝提示。
func TestRunDaemon_RefusesWhenInstanceRunning(t *testing.T) {
	saveFlagVars(t)

	child := exec.Command("sleep", "30")
	if err := child.Start(); err != nil {
		t.Fatalf("启动子进程失败: %v", err)
	}
	t.Cleanup(func() {
		if child.ProcessState == nil {
			_ = child.Process.Kill()
			_, _ = child.Process.Wait()
		}
	})

	pidFile = filepath.Join(t.TempDir(), "agent.pid")
	if err := os.WriteFile(pidFile, []byte(strconv.Itoa(child.Process.Pid)+"\n"), 0o644); err != nil {
		t.Fatalf("write pid file: %v", err)
	}

	err := runDaemon()
	if err == nil {
		t.Fatal("expected runDaemon to refuse when an instance is running")
	}
	if !strings.Contains(err.Error(), "daemon 已经在运行") {
		t.Errorf("error = %v, want 'daemon 已经在运行'", err)
	}
}
