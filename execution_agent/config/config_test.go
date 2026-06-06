package config

import (
	"os"
	"testing"
)

func TestDefaultConfig_ServerURL(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.ServerURL != "ws://localhost:26521/api/ws/agent" {
		t.Errorf("expected ws://localhost:26521/api/ws/agent, got %s", cfg.ServerURL)
	}
}

func TestDefaultConfig_AgentID(t *testing.T) {
	cfg := DefaultConfig()
	hostname, _ := os.Hostname()
	if cfg.AgentID != hostname {
		t.Errorf("expected %s, got %s", hostname, cfg.AgentID)
	}
}

func TestDefaultConfig_Shell(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Shell != "/bin/bash" {
		t.Errorf("expected /bin/bash, got %s", cfg.Shell)
	}
}

func TestDefaultConfig_PidFile(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.PidFile != "/var/run/taskpps-agent.pid" {
		t.Errorf("expected /var/run/taskpps-agent.pid, got %s", cfg.PidFile)
	}
}

func TestDefaultConfig_LogFile(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.LogFile != "/var/log/taskpps-agent.log" {
		t.Errorf("expected /var/log/taskpps-agent.log, got %s", cfg.LogFile)
	}
}

func TestDefaultConfig_Secret(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Secret != "" {
		t.Errorf("expected empty secret, got %s", cfg.Secret)
	}
}

func TestDefaultConfig_WorkDir(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.WorkDir != "" {
		t.Errorf("expected empty workdir, got %s", cfg.WorkDir)
	}
}

func TestDefaultConfig_Daemon(t *testing.T) {
	cfg := DefaultConfig()
	if cfg.Daemon {
		t.Errorf("expected daemon to be false")
	}
}

func TestConfig_ModifyFields(t *testing.T) {
	cfg := DefaultConfig()
	cfg.ServerURL = "ws://custom:9999/api/ws/agent"
	cfg.AgentID = "custom-agent"
	cfg.Secret = "secret123"
	cfg.Shell = "/bin/sh"
	cfg.WorkDir = "/custom/workdir"
	cfg.PidFile = "/custom/pid"
	cfg.LogFile = "/custom/log"
	cfg.Daemon = true

	if cfg.ServerURL != "ws://custom:9999/api/ws/agent" {
		t.Errorf("expected custom URL")
	}
	if cfg.AgentID != "custom-agent" {
		t.Errorf("expected custom-agent")
	}
	if cfg.Secret != "secret123" {
		t.Errorf("expected secret123")
	}
	if cfg.Shell != "/bin/sh" {
		t.Errorf("expected /bin/sh")
	}
	if cfg.WorkDir != "/custom/workdir" {
		t.Errorf("expected /custom/workdir")
	}
	if cfg.PidFile != "/custom/pid" {
		t.Errorf("expected /custom/pid")
	}
	if cfg.LogFile != "/custom/log" {
		t.Errorf("expected /custom/log")
	}
	if !cfg.Daemon {
		t.Errorf("expected daemon true")
	}
}