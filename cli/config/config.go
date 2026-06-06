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
	WorkDir  string            `mapstructure:"workdir"`
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
		if _, err := os.Stat(filepath.Join(dir, ".taskpps", "taskpps.yaml")); err == nil {
			return dir, nil
		}
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

func FindWorkDir(projectFlag string) (string, error) {
	if projectFlag != "" {
		return filepath.Abs(projectFlag)
	}

	if envDir := os.Getenv("TASKPPS_WORKDIR"); envDir != "" {
		return filepath.Abs(envDir)
	}

	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for i := 0; i < 10; i++ {
		configPath := filepath.Join(dir, ".taskpps", "taskpps.yaml")
		if _, statErr := os.Stat(configPath); statErr == nil {
			v := viper.New()
			v.SetConfigFile(configPath)
			if readErr := v.ReadInConfig(); readErr == nil {
				workdir := v.GetString("workdir")
				if workdir != "" {
					return filepath.Abs(workdir)
				}
			}
			return filepath.Abs(dir)
		}
		if _, statErr := os.Stat(filepath.Join(dir, "taskpps.yaml")); statErr == nil {
			v := viper.New()
			v.SetConfigFile(filepath.Join(dir, "taskpps.yaml"))
			if readErr := v.ReadInConfig(); readErr == nil {
				workdir := v.GetString("workdir")
				if workdir != "" {
					return filepath.Abs(workdir)
				}
			}
			return filepath.Abs(dir)
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	return "", fmt.Errorf("未找到项目工作目录，请设置 TASKPPS_WORKDIR 环境变量或使用 --project 参数指定")
}

func Load(path string, projectFlag string) (*Config, error) {
	v := viper.New()
	v.SetConfigType("yaml")

	if path != "" {
		v.SetConfigFile(path)
	} else {
		workDir, err := FindWorkDir(projectFlag)
		if err != nil {
			return nil, err
		}
		configPath := filepath.Join(workDir, ".taskpps", "taskpps.yaml")
		if _, statErr := os.Stat(configPath); statErr != nil {
			configPath = filepath.Join(workDir, "taskpps.yaml")
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
