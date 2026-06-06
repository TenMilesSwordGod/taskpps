package logger

import (
	"fmt"
	"io"
	"log"
	"os"
	"sync"
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
	mu           sync.RWMutex
	currentLevel LogLevel = LevelNone
	debugLogger  *log.Logger
	infoLogger   *log.Logger
	warnLogger   *log.Logger
	errorLogger  *log.Logger
	logFile      *os.File
)

func init() {
	debugLogger = log.New(io.Discard, "[DEBUG] ", log.LstdFlags|log.Lshortfile)
	infoLogger = log.New(io.Discard, "[INFO]  ", log.LstdFlags|log.Lshortfile)
	warnLogger = log.New(io.Discard, "[WARN]  ", log.LstdFlags|log.Lshortfile)
	errorLogger = log.New(io.Discard, "[ERROR] ", log.LstdFlags|log.Lshortfile)
}

func (l LogLevel) String() string {
	if name, ok := levelNames[l]; ok {
		return name
	}
	return fmt.Sprintf("LEVEL(%d)", l)
}

func SetOutput(w io.Writer) {
	debugLogger.SetOutput(w)
	infoLogger.SetOutput(w)
	warnLogger.SetOutput(w)
	errorLogger.SetOutput(w)
}

func SetLogFile(filename string) error {
	if logFile != nil {
		logFile.Close()
	}
	var err error
	logFile, err = os.OpenFile(filename, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return err
	}
	SetOutput(logFile)
	return nil
}

func SetLevel(v int) {
	mu.Lock()
	defer mu.Unlock()
	switch {
	case v <= 0:
		currentLevel = LevelNone
	case v == 1:
		currentLevel = LevelError
	case v == 2:
		currentLevel = LevelWarn
	case v == 3:
		currentLevel = LevelInfo
	default:
		currentLevel = LevelDebug
	}
}

func SetLevelByName(name string) bool {
	mu.Lock()
	defer mu.Unlock()
	level, ok := levelByName[name]
	if !ok {
		return false
	}
	currentLevel = level
	return true
}

func GetLevel() LogLevel {
	mu.RLock()
	defer mu.RUnlock()
	return currentLevel
}

func EnableVerboseOutput() {
	SetOutput(os.Stderr)
}

func Debug(format string, v ...interface{}) {
	mu.RLock()
	level := currentLevel
	mu.RUnlock()
	if level >= LevelDebug {
		debugLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Info(format string, v ...interface{}) {
	mu.RLock()
	level := currentLevel
	mu.RUnlock()
	if level >= LevelInfo {
		infoLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Warn(format string, v ...interface{}) {
	mu.RLock()
	level := currentLevel
	mu.RUnlock()
	if level >= LevelWarn {
		warnLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Error(format string, v ...interface{}) {
	mu.RLock()
	level := currentLevel
	mu.RUnlock()
	if level >= LevelError {
		errorLogger.Output(2, fmt.Sprintf(format, v...))
	}
}

func Fatal(format string, v ...interface{}) {
	errorLogger.Output(2, fmt.Sprintf(format, v...))
	os.Exit(1)
}