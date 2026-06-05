package config

import (
	"os"
)

type Config struct {
	ServerURL string
	AgentID   string
	Secret    string
	Shell     string
	PidFile   string
	LogFile   string
	Daemon    bool
}

func DefaultConfig() *Config {
	hostname, _ := os.Hostname()
	return &Config{
		ServerURL: "ws://localhost:28765",
		AgentID:   hostname,
		Secret:    "",
		Shell:     "/bin/bash",
		PidFile:   "/var/run/taskpps-agent.pid",
		LogFile:   "/var/log/taskpps-agent.log",
		Daemon:    false,
	}
}
