package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

var (
	// 版本信息，编译时可以通过 ldflags 注入
	Version = "0.1.0"
)

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Show ppsctl version information",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Printf("ppsctl version %s\n", Version)
	},
}

func init() {
	RootCmd.AddCommand(versionCmd)
}

func CheckVersionMismatch(serverVersion string) error {
	if serverVersion == "" {
		return nil
	}
	if Version != serverVersion {
		fmt.Fprintf(os.Stderr, "WARNING: Version mismatch! CLI (%s) != Server (%s)\n", Version, serverVersion)
	}
	return nil
}
