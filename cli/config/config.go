package config

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/spf13/viper"
)

var App *Config

type Config struct {
	Server   ServerConfig      `mapstructure:"server"`
	Executor ExecutorConfig    `mapstructure:"executor"`
	Env      map[string]string `mapstructure:"env"`
}

type ServerConfig struct {
	Host string `mapstructure:"host"`
	Port int    `mapstructure:"port"`
}

type ExecutorConfig struct {
	DefaultTimeout int    `mapstructure:"default_timeout"`
	MaxWorkers     int    `mapstructure:"max_workers"`
	Shell          string `mapstructure:"shell"`
}

func FindProjectRoot() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for i := 0; i < 10; i++ {
		// Check .taskpps/taskpps.yaml first
		if _, err := os.Stat(filepath.Join(dir, ".taskpps", "taskpps.yaml")); err == nil {
			return dir, nil
		}
		// Fallback to root taskpps.yaml for backward compatibility
		if _, err := os.Stat(filepath.Join(dir, "taskpps.yaml")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	return "", fmt.Errorf("taskpps.yaml not found in current or parent directories")
}

func Load(path string) (*Config, error) {
	v := viper.New()
	v.SetConfigType("yaml")

	if path != "" {
		v.SetConfigFile(path)
	} else {
		root, err := FindProjectRoot()
		if err != nil {
			return nil, err
		}
		// Try .taskpps/taskpps.yaml first, then root taskpps.yaml
		configPath := filepath.Join(root, ".taskpps", "taskpps.yaml")
		if _, err := os.Stat(configPath); err != nil {
			configPath = filepath.Join(root, "taskpps.yaml")
		}
		v.SetConfigFile(configPath)
	}

	v.SetDefault("server.host", "127.0.0.1")
	v.SetDefault("server.port", 26521)
	v.SetDefault("executor.default_timeout", 3600)
	v.SetDefault("executor.max_workers", 10)
	v.SetDefault("executor.shell", "/bin/bash")

	if err := v.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, fmt.Errorf("failed to read config: %w", err)
		}
	}

	cfg := &Config{}
	if err := v.Unmarshal(cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}
	App = cfg
	return cfg, nil
}

func GetServerAddr(cfg *Config) string {
	return fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.Port)
}
