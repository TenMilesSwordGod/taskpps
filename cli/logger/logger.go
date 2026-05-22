package logger

import (
	"fmt"
	"io"
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
	logFile     *os.File
)

func init() {
	// Default to no output at all (io.Discard)
	debugLogger = log.New(io.Discard, "[DEBUG] ", log.LstdFlags|log.Lshortfile)
	infoLogger = log.New(io.Discard, "[INFO]  ", log.LstdFlags|log.Lshortfile)
	warnLogger = log.New(io.Discard, "[WARN]  ", log.LstdFlags|log.Lshortfile)
	errorLogger = log.New(io.Discard, "[ERROR] ", log.LstdFlags|log.Lshortfile)
}

// SetOutput sets the log output destination (file or os.Stderr etc.)
func SetOutput(w io.Writer) {
	debugLogger.SetOutput(w)
	infoLogger.SetOutput(w)
	warnLogger.SetOutput(w)
	errorLogger.SetOutput(w)
}

// SetLogFile sets the log output to a file
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

// EnableVerboseOutput enables output to stderr (for when verbose flag is set)
func EnableVerboseOutput() {
	SetOutput(os.Stderr)
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
