package agent

import (
	"bufio"
	"io"
	"os"
	"strconv"
	"strings"
	"syscall"
)

func collectDescendants(pid int) []int {
	var descendants []int
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return descendants
	}
	for _, entry := range entries {
		if !isDigit(entry.Name()) {
			continue
		}
		childPid, err := strconv.Atoi(entry.Name())
		if err != nil || childPid == pid {
			continue
		}
		ppid := readPPID(childPid)
		if ppid == pid {
			descendants = append(descendants, childPid)
			descendants = append(descendants, collectDescendants(childPid)...)
		}
	}
	return descendants
}

func readPPID(pid int) int {
	data, err := os.ReadFile("/proc/" + strconv.Itoa(pid) + "/stat")
	if err != nil {
		return 0
	}
	stat := string(data)
	closeParen := strings.LastIndex(stat, ") ")
	if closeParen == -1 {
		return 0
	}
	fields := strings.Fields(stat[closeParen+2:])
	if len(fields) < 2 {
		return 0
	}
	ppid, _ := strconv.Atoi(fields[1])
	return ppid
}

func killProcessTree(pid int, sig syscall.Signal) {
	pids := append([]int{pid}, collectDescendants(pid)...)
	for i := len(pids) - 1; i >= 0; i-- {
		syscall.Kill(pids[i], sig)
	}
}

func isDigit(s string) bool {
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return len(s) > 0
}

func readPipeBinary(reader io.Reader) <-chan []byte {
	// 较大的缓冲是为了让 readPipe 领先 streamOutput 的 WebSocket 发送，
	// 避免在任务输出大量日志时 channel 写满导致管道被回压、子进程 write
	// 阻塞、最终 cmd.Wait() 永远不返回、exec_result 发不出去 (issue #16)。
	ch := make(chan []byte, 8192)
	go func() {
		defer close(ch)
		buf := bufio.NewReader(reader)
		for {
			line, err := buf.ReadBytes('\n')
			if len(line) > 0 {
				ch <- line
			}
			if err != nil {
				return
			}
		}
	}()
	return ch
}

func signalNameFromState(state *os.ProcessState) string {
	if state == nil {
		return ""
	}
	ws := state.Sys().(syscall.WaitStatus)
	if ws.Signaled() {
		sig := ws.Signal()
		return signalToString(sig)
	}
	return ""
}

func signalToString(sig syscall.Signal) string {
	switch sig {
	case syscall.SIGHUP:
		return "SIGHUP"
	case syscall.SIGINT:
		return "SIGINT"
	case syscall.SIGQUIT:
		return "SIGQUIT"
	case syscall.SIGILL:
		return "SIGILL"
	case syscall.SIGABRT:
		return "SIGABRT"
	case syscall.SIGFPE:
		return "SIGFPE"
	case syscall.SIGKILL:
		return "SIGKILL"
	case syscall.SIGSEGV:
		return "SIGSEGV"
	case syscall.SIGPIPE:
		return "SIGPIPE"
	case syscall.SIGALRM:
		return "SIGALRM"
	case syscall.SIGTERM:
		return "SIGTERM"
	default:
		return sig.String()
	}
}
