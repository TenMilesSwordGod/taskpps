package main

import (
	"fmt"
	"os"

	"github.com/taskpps/execution-agent/cmd"
)

func main() {
	if err := cmd.RootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
