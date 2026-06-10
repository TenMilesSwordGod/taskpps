package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestGetServerAddr(t *testing.T) {
	cfg := &Config{
		Server: ServerConfig{
			Host: "example.com",
			Port: 8080,
		},
	}

	addr := GetServerAddr(cfg)
	expected := "example.com:8080"

	if addr != expected {
		t.Errorf("GetServerAddr() = %s, want %s", addr, expected)
	}
}

func TestGetServerAddrWithPortZero(t *testing.T) {
	cfg := &Config{
		Server: ServerConfig{
			Host: "10.98.72.23:8418",
			Port: 0,
		},
	}

	addr := GetServerAddr(cfg)
	expected := "10.98.72.23:8418"

	if addr != expected {
		t.Errorf("GetServerAddr() = %s, want %s", addr, expected)
	}
}

func TestLoadWithoutProjectDir(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "test-noproject")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	originalWd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	os.Chdir(tmpDir)
	defer os.Chdir(originalWd)

	cfg, err := Load("", "")
	if err != nil {
		t.Fatalf("Load() should not error without project dir, got: %v", err)
	}

	if cfg.Server.Host != "127.0.0.1" {
		t.Errorf("cfg.Server.Host = %s, want 127.0.0.1", cfg.Server.Host)
	}
	if cfg.Server.Port != 26521 {
		t.Errorf("cfg.Server.Port = %d, want 26521", cfg.Server.Port)
	}
}

func TestLoadWithDefaults(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "test-config")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	configContent := `
server:
  host: test.example.com
  port: 9090
executor:
  default_timeout: 1800
  max_workers: 5
`
	configPath := filepath.Join(tmpDir, "taskpps.yaml")
	err = os.WriteFile(configPath, []byte(configContent), 0644)
	if err != nil {
		t.Fatal(err)
	}

	originalWd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	os.Chdir(tmpDir)
	defer os.Chdir(originalWd)

	cfg, err := Load(configPath, "")
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if cfg.Server.Host != "test.example.com" {
		t.Errorf("cfg.Server.Host = %s, want test.example.com", cfg.Server.Host)
	}
	if cfg.Server.Port != 9090 {
		t.Errorf("cfg.Server.Port = %d, want 9090", cfg.Server.Port)
	}
	if cfg.Executor.DefaultTimeout != 1800 {
		t.Errorf("cfg.Executor.DefaultTimeout = %d, want 1800", cfg.Executor.DefaultTimeout)
	}
	if cfg.Executor.MaxWorkers != 5 {
		t.Errorf("cfg.Executor.MaxWorkers = %d, want 5", cfg.Executor.MaxWorkers)
	}
}

func TestFindProjectRoot(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "test-project")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tmpDir)

	testFile := filepath.Join(tmpDir, "taskpps.yaml")
	err = os.WriteFile(testFile, []byte(""), 0644)
	if err != nil {
		t.Fatal(err)
	}

	originalWd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	os.Chdir(tmpDir)
	defer os.Chdir(originalWd)

	root, err := FindProjectRoot()
	if err != nil {
		t.Fatalf("FindProjectRoot() error = %v", err)
	}

	if root != tmpDir {
		t.Errorf("FindProjectRoot() = %s, want %s", root, tmpDir)
	}
}
