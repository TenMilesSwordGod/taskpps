package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestFindProjectRoot_NotFound(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-noroot-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	oldDir, _ := os.Getwd()
	os.Chdir(dir)
	defer os.Chdir(oldDir)

	_, err = FindProjectRoot()
	if err == nil {
		t.Error("expected error when no taskpps.yaml found")
	}
}

func TestFindProjectRoot_FoundWithTaskppsYaml(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-root-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	configFile := filepath.Join(dir, "taskpps.yaml")
	if err := os.WriteFile(configFile, []byte("server:\n  host: 127.0.0.1\n"), 0644); err != nil {
		t.Fatal(err)
	}

	oldDir, _ := os.Getwd()
	os.Chdir(dir)
	defer os.Chdir(oldDir)

	root, err := FindProjectRoot()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if root != dir {
		t.Errorf("expected %s, got %s", dir, root)
	}
}

func TestFindProjectRoot_FoundWithDotTaskpps(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-dotroot-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	dotDir := filepath.Join(dir, ".taskpps")
	if err := os.MkdirAll(dotDir, 0755); err != nil {
		t.Fatal(err)
	}
	configFile := filepath.Join(dotDir, "taskpps.yaml")
	if err := os.WriteFile(configFile, []byte("server:\n  host: 127.0.0.1\n"), 0644); err != nil {
		t.Fatal(err)
	}

	oldDir, _ := os.Getwd()
	os.Chdir(dir)
	defer os.Chdir(oldDir)

	root, err := FindProjectRoot()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if root != dir {
		t.Errorf("expected %s, got %s", dir, root)
	}
}

func TestFindProjectRoot_ParentDir(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-parent-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	configFile := filepath.Join(dir, "taskpps.yaml")
	if err := os.WriteFile(configFile, []byte("server:\n  host: 127.0.0.1\n"), 0644); err != nil {
		t.Fatal(err)
	}

	subDir := filepath.Join(dir, "sub", "deep")
	if err := os.MkdirAll(subDir, 0755); err != nil {
		t.Fatal(err)
	}

	oldDir, _ := os.Getwd()
	os.Chdir(subDir)
	defer os.Chdir(oldDir)

	root, err := FindProjectRoot()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if root != dir {
		t.Errorf("expected %s, got %s", dir, root)
	}
}

func TestGetServerAddr_Default(t *testing.T) {
	cfg := &Config{
		Server: ServerConfig{
			Host: "127.0.0.1",
			Port: 26521,
		},
	}
	addr := GetServerAddr(cfg)
	if addr != "127.0.0.1:26521" {
		t.Errorf("expected 127.0.0.1:26521, got %s", addr)
	}
}

func TestGetServerAddr_Custom(t *testing.T) {
	cfg := &Config{
		Server: ServerConfig{
			Host: "0.0.0.0",
			Port: 8080,
		},
	}
	addr := GetServerAddr(cfg)
	if addr != "0.0.0.0:8080" {
		t.Errorf("expected 0.0.0.0:8080, got %s", addr)
	}
}

func TestGetServerAddr_ZeroPort(t *testing.T) {
	cfg := &Config{
		Server: ServerConfig{
			Host: "localhost",
			Port: 0,
		},
	}
	addr := GetServerAddr(cfg)
	if addr != "localhost:0" {
		t.Errorf("expected localhost:0, got %s", addr)
	}
}

func TestLoad_ConfigWithEnv(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-config-env-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	configContent := `
server:
  host: "0.0.0.0"
  port: 9999
executor:
  default_timeout: 120
  max_workers: 8
  shell: "/bin/sh"
workdir: "/tmp/test"
`
	configFile := filepath.Join(dir, "taskpps.yaml")
	if err := os.WriteFile(configFile, []byte(configContent), 0644); err != nil {
		t.Fatal(err)
	}

	cfg, err := Load(configFile, "")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.Server.Host != "0.0.0.0" {
		t.Errorf("expected host 0.0.0.0, got %s", cfg.Server.Host)
	}
	if cfg.Server.Port != 9999 {
		t.Errorf("expected port 9999, got %d", cfg.Server.Port)
	}
	if cfg.Executor.DefaultTimeout != 120 {
		t.Errorf("expected timeout 120, got %d", cfg.Executor.DefaultTimeout)
	}
	if cfg.Executor.MaxWorkers != 8 {
		t.Errorf("expected max workers 8, got %d", cfg.Executor.MaxWorkers)
	}
}

func TestLoad_InvalidConfig(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-config-invalid-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	configFile := filepath.Join(dir, "invalid.yaml")
	if err := os.WriteFile(configFile, []byte(":invalid yaml: [[["), 0644); err != nil {
		t.Fatal(err)
	}

	_, err = Load(configFile, "")
	if err == nil {
		t.Error("expected error for invalid config")
	}
}

func TestFindWorkDir_WithProjectFlag(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-workdir-flag-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	workDir, err := FindWorkDir(dir)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	absDir, _ := filepath.Abs(dir)
	if workDir != absDir {
		t.Errorf("expected %s, got %s", absDir, workDir)
	}
}

func TestFindWorkDir_EnvVar(t *testing.T) {
	dir, err := os.MkdirTemp("", "test-workdir-env-*")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(dir)

	os.Setenv("TASKPPS_WORKDIR", dir)
	defer os.Unsetenv("TASKPPS_WORKDIR")

	workDir, err := FindWorkDir("")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	absDir, _ := filepath.Abs(dir)
	if workDir != absDir {
		t.Errorf("expected %s, got %s", absDir, workDir)
	}
}

func TestConfig_Defaults(t *testing.T) {
	cfg := &Config{}
	if cfg.Server.Host != "" {
		t.Errorf("expected empty host, got %s", cfg.Server.Host)
	}
	if cfg.Server.Port != 0 {
		t.Errorf("expected port 0, got %d", cfg.Server.Port)
	}
}

func TestExecutorConfig_Defaults(t *testing.T) {
	cfg := ExecutorConfig{}
	if cfg.DefaultTimeout != 0 {
		t.Errorf("expected timeout 0, got %d", cfg.DefaultTimeout)
	}
	if cfg.MaxWorkers != 0 {
		t.Errorf("expected max workers 0, got %d", cfg.MaxWorkers)
	}
}