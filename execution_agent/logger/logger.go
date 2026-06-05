package logger

import (
	"fmt"
	"io"
	"log"
	"os"
	"time"
)

var (
	stdLogger  *log.Logger
	fileLogger *log.Logger
	logFile    *os.File
)

func Init(logPath string) error {
	if logPath == "" {
		stdLogger = log.New(os.Stderr, "", 0)
		return nil
	}

	f, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return fmt.Errorf("failed to open log file %s: %w", logPath, err)
	}
	logFile = f

	writer := io.MultiWriter(os.Stderr, f)
	stdLogger = log.New(writer, "", 0)
	fileLogger = log.New(f, "", 0)
	return nil
}

func Close() {
	if logFile != nil {
		logFile.Close()
	}
}

func logf(level, format string, args ...interface{}) {
	msg := fmt.Sprintf(format, args...)
	line := fmt.Sprintf("[%s] [%s] %s", time.Now().Format(time.RFC3339), level, msg)
	if stdLogger != nil {
		stdLogger.Println(line)
	}
}

func Info(format string, args ...interface{}) {
	logf("INFO", format, args...)
}

func Warn(format string, args ...interface{}) {
	logf("WARN", format, args...)
}

func Error(format string, args ...interface{}) {
	logf("ERROR", format, args...)
}

func Debug(format string, args ...interface{}) {
	logf("DEBUG", format, args...)
}
