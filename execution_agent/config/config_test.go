package config

import (
	"os"
	"testing"
)

// TestDefaultConfig 合并了原先 8 个 TestDefaultConfig_* 单字段用例。
// 表驱动断言 DefaultConfig 的所有对外默认值，任一字段被改坏都会失败。
func TestDefaultConfig(t *testing.T) {
	cfg := DefaultConfig()
	hostname, _ := os.Hostname()

	checks := []struct {
		name string
		got  string
		want string
	}{
		{"ServerURL", cfg.ServerURL, "ws://localhost:26521/api/ws/agent"},
		{"AgentID", cfg.AgentID, hostname},
		{"Secret", cfg.Secret, ""},
		{"Shell", cfg.Shell, "/bin/bash"},
		{"WorkDir", cfg.WorkDir, ""},
		{"PidFile", cfg.PidFile, "/var/run/taskpps-agent.pid"},
		{"LogFile", cfg.LogFile, "/var/log/taskpps-agent.log"},
	}
	for _, c := range checks {
		if c.got != c.want {
			t.Errorf("DefaultConfig().%s = %q, want %q", c.name, c.got, c.want)
		}
	}

	if cfg.Daemon {
		t.Error("DefaultConfig().Daemon = true, want false")
	}
}
