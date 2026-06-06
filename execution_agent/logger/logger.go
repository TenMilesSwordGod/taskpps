package logger

import (
	"fmt"
	"io"
	"log"
	"os"
	"sync"
	"time"
)

type LogLevel int

const (
	LevelNone  LogLevel = iota
	LevelError
	LevelWarn
	LevelInfo
	LevelDebug
)

var levelNames = map[LogLevel]string{
	LevelNone:  "NONE",
	LevelError: "ERROR",
	LevelWarn:  "WARN",
	LevelInfo:  "INFO",
	LevelDebug: "DEBUG",
}

var levelByName = map[string]LogLevel{
	"NONE":  LevelNone,
	"ERROR": LevelError,
	"WARN":  LevelWarn,
	"INFO":  LevelInfo,
	"DEBUG": LevelDebug,
}

var (
	mu      sync.RWMutex
	level   LogLevel = LevelInfo
	writer  *log.Logger
	logFile *os.File
)

func (l LogLevel) String() string {
	if name, ok := levelNames[l]; ok {
		return name
	}
	return fmt.Sprintf("LEVEL(%d)", l)
}

func Init(logPath string) error {
	if logPath == "" {
		writer = log.New(os.Stderr, "", 0)
		return nil
	}

	f, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("failed to open log file %s: %w", logPath, err)
	}
	logFile = f

	multi := io.MultiWriter(os.Stderr, f)
	writer = log.New(multi, "", 0)
	return nil
}

func Close() error {
	if logFile != nil {
		err := logFile.Close()
		logFile = nil
		return err
	}
	return nil
}

func SetLevel(v int) {
	mu.Lock()
	defer mu.Unlock()
	switch {
	case v <= 0:
		level = LevelNone
	case v == 1:
		level = LevelError
	case v == 2:
		level = LevelWarn
	case v == 3:
		level = LevelInfo
	default:
		level = LevelDebug
	}
}

func SetLevelByName(name string) bool {
	mu.Lock()
	defer mu.Unlock()
	l, ok := levelByName[name]
	if !ok {
		return false
	}
	level = l
	return true
}

func GetLevel() LogLevel {
	mu.RLock()
	defer mu.RUnlock()
	return level
}

func logf(logLevel LogLevel, levelName, format string, args ...interface{}) {
	mu.RLock()
	currentLevel := level
	w := writer
	mu.RUnlock()

	if currentLevel < logLevel {
		return
	}
	if w == nil {
		return
	}

	msg := fmt.Sprintf(format, args...)
	line := fmt.Sprintf("[%s] [%s] %s", time.Now().Format(time.RFC3339), levelName, msg)
	w.Println(line)
}

func Debug(format string, args ...interface{}) {
	logf(LevelDebug, "DEBUG", format, args...)
}

func Info(format string, args ...interface{}) {
	logf(LevelInfo, "INFO", format, args...)
}

func Warn(format string, args ...interface{}) {
	logf(LevelWarn, "WARN", format, args...)
}

func Error(format string, args ...interface{}) {
	logf(LevelError, "ERROR", format, args...)
}