package logger

import (
	"fmt"
	"log"
	"os"
)

type LogLevel int

const (
	LevelNone  LogLevel = iota  // No logs at all (default)
	LevelError LogLevel = iota // Errors only
	LevelWarn  LogLevel = iota // Warnings and Errors
	LevelInfo  LogLevel = iota // Info, Warnings and Errors
	LevelDebug LogLevel = iota // All including debug
)

var (
	currentLevel LogLevel = LevelNone
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
		currentLevel = LevelNone
	case 1:
		currentLevel = LevelError
	case 2:
		currentLevel = LevelWarn
	case 3:
		currentLevel = LevelInfo
	case 4:
		fallthrough
	default:
		if v >4 {
			currentLevel = LevelDebug
		} else if v ==4 {
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
