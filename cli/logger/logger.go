package logger

import (
	"fmt"
	"log"
	"os"
)

type LogLevel int

const (
	LevelError LogLevel = iota // Errors only
	LevelWarn  LogLevel = iota // Warnings and Errors
	LevelInfo  LogLevel = iota // Info, Warnings and Errors
	LevelDebug LogLevel = iota // All including debug
)

var (
	currentLevel LogLevel = LevelError
	debugLogger *log.Logger
	infoLogger  *log.Logger
	warnLogger  *log.Logger
	errorLogger *log.Logger
)

func init() {
	debugLogger = log.New(os.Stderr, "[DEBUG] ", log.LstdFlags|log.Lshortfile)
	infoLogger = log.New(os.Stderr, "[INFO]  ", log.LstdFlags|log.Lshortfile)
	warnLogger = log.New(os.Stderr, "[WARN]  ", log.LstdFlags|log.Lshortfile)
	errorLogger = log.New(os.Stderr, "[ERROR] ", log.LstdFlags|log.Lshortfile)
}

func SetLevel(v int) {
	switch v {
	case 0:
		currentLevel = LevelError
	case 1:
		currentLevel = LevelWarn
	case 2:
		currentLevel = LevelInfo
	case 3:
		currentLevel = LevelDebug
	default:
		if v >3 {
			currentLevel = LevelDebug
		}
	}
}

func Debug(format string, v ...interface{}) {
	if currentLevel >= LevelDebug {
		debugLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Info(format string, v ...interface{}) {
	if currentLevel >= LevelInfo {
		infoLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Warn(format string, v ...interface{}) {
	if currentLevel >= LevelWarn {
		warnLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Error(format string, v ...interface{}) {
	if currentLevel >= LevelError {
		errorLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Fatal(format string, v ...interface{}) {
	errorLogger.Output(2, fmt.Sprintf(format, v...))
	os.Exit(1)
}
