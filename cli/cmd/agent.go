package cmd

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/fatih/color"
	"github.com/olekukonko/tablewriter"
	"github.com/spf13/cobra"
	"github.com/taskpps/ppsctl/models"
)

var (
	agentTimeout     int
	agentFile        string
	agentExecTimeout int
	agentExecCwd     string
)

var agentCmd = &cobra.Command{
	Use:   "agent",
	Short: "Manage and check agent connections",
	Long: `Manage agents and check their connectivity.

支持两种格式:
  长格式:  ppsctl agent <action> <agent-id> [flags]
  快捷:    ppsctl agent <agent-id> [<action>]         # 无 action 默认为 status

示例:
  ppsctl agent test-agent01                            # 查看状态 (= agent status test-agent01)
  ppsctl agent test-agent01 status                     # 查看状态
  ppsctl agent test-agent01 exec -- echo hello         # 执行命令
  ppsctl agent test-agent01 deploy                     # 部署
  ppsctl agent test-agent01 try-connect                # 尝试连接
  ppsctl agent test-agent01 check                      # 检查连接

Subcommands (长格式):
  try-connect  Test connectivity to a specific agent
  check        Check all agent connections, grouped by file`,
	Args: cobra.ArbitraryArgs,
	RunE: func(cmd *cobra.Command, args []string) error {
		if len(args) == 0 {
			return cmd.Help()
		}

		actions := map[string]bool{
			"try-connect": true,
			"check":       true,
			"list":        true,
			"status":      true,
			"deploy":      true,
			"exec":        true,
		}

		if actions[args[0]] {
			return cmd.Help()
		}

		agentID := args[0]
		action := "status"
		remaining := args[1:]
		if len(remaining) > 0 && actions[remaining[0]] {
			action = remaining[0]
			remaining = remaining[1:]
		}

		switch action {
		case "status":
			return runAgentStatus(agentID)
		case "list":
			return runAgentList()
		case "deploy":
			return runAgentDeploy(agentID)
		case "try-connect":
			return runAgentTryConnect(agentID)
		case "check":
			return runAgentCheck(agentID, agentFile)
		case "exec":
			if len(remaining) == 0 {
				return fmt.Errorf("exec 需要命令参数,用法: ppsctl agent %s exec -- <command>", agentID)
			}
			return runAgentExec(agentID, remaining)
		default:
			return fmt.Errorf("未知操作 '%s',可用: status, list, deploy, try-connect, check, exec", action)
		}
	},
}

var agentTryConnectCmd = &cobra.Command{
	Use:   "try-connect <agent-id>",
	Short: "Test connectivity to a specific agent",
	Long: `Attempt a TCP connection to the specified agent and report the result.

示例:
  ppsctl agent try-connect prod-server
  ppsctl agent try-connect prod-server --timeout 10`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAgentTryConnect(args[0])
	},
}

var agentCheckCmd = &cobra.Command{
	Use:   "check [agent-id]",
	Short: "Check agent connections with live progress",
	Long: `检查一个或所有 agent 的连接状态,支持实时进度显示。

示例:
  ppsctl agent check                     检查所有 agent
  ppsctl agent check prod-server         检查指定 agent
  ppsctl agent check --file staging      仅检查 staging.yaml 中的 agent`,
	Args: cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		agentID := ""
		if len(args) > 0 {
			agentID = args[0]
		}
		return runAgentCheck(agentID, agentFile)
	},
}

func runAgentTryConnect(agentID string) error {
	result, err := apiClient.TryConnect(agentID, agentTimeout)
	if err != nil {
		return err
	}

	printSingleResult(result)
	if result.Status == "failed" {
		os.Exit(1)
	}
	return nil
}

func runAgentCheck(agentID string, fileFilter string) error {
	var results []models.AgentCheckResult
	var cnt int

	summary, err := apiClient.CheckAgentsStream(agentID, fileFilter, agentTimeout, func(r models.AgentCheckResult) {
		results = append(results, r)
		cnt++
		fmt.Printf("\r\033[K")
		if r.Status == "failed" || r.Status == "disconnected" {
			color.Red("[%d] ✗ %s (%s:%d) — %s", cnt, r.AgentID, r.Host, r.Port, r.Status)
			if r.Error != "" {
				fmt.Printf(": %s", r.Error)
			}
			fmt.Println()
		} else {
			extra := ""
			if r.System != "" || r.Arch != "" {
				extra = fmt.Sprintf(" · %s/%s", color.CyanString(orUnknown(r.System)), color.CyanString(orUnknown(r.Arch)))
			}
			color.Green("[%d] ✓ %s (%s:%d) — %s in %dms%s", cnt, r.AgentID, r.Host, r.Port, r.Status, r.LatencyMs, extra)
			fmt.Println()
		}
	})

	if err != nil && strings.Contains(err.Error(), "404") {
		response, err2 := apiClient.CheckAgents(agentID, fileFilter, agentTimeout)
		if err2 != nil {
			return err2
		}
		results = response.Results
		summary = &response.Summary
	} else if err != nil {
		return err
	}

	if len(results) == 0 {
		fmt.Println("No agents found.")
		return nil
	}

	fmt.Println()

	if len(results) == 1 {
		printSingleResult(&results[0])
	} else {
		printCheckResultsGrouped(results, summary)
	}

	if summary.Failed > 0 {
		os.Exit(1)
	}
	return nil
}

func runAgentList() error {
	agents, err := apiClient.AgentList()
	if err != nil {
		return err
	}
	if len(agents) == 0 {
		fmt.Println("没有已连接的 agent")
		return nil
	}

	color.Cyan("───── Agents ─────")
	table := tablewriter.NewWriter(os.Stdout)
	table.SetHeader([]string{"Agent ID", "Hostname", "Platform", "Version", "PID", "Tasks"})
	table.SetBorder(false)
	table.SetColumnSeparator(" ")
	for _, a := range agents {
		table.Append([]string{
			a.AgentID,
			a.Hostname,
			a.Platform,
			a.AgentVersion,
			fmt.Sprintf("%d", a.AgentPID),
			fmt.Sprintf("%d", a.RunningCommands),
		})
	}
	table.Render()
	fmt.Printf("\nTotal: %d agents connected\n", len(agents))
	return nil
}

func runAgentStatus(agentID string) error {
	result, err := apiClient.AgentStatus(agentID)
	if err != nil {
		return err
	}

	fmt.Printf("───── Agent Status ─────\n")
	fmt.Printf("  Agent ID:       %s\n", result.AgentID)
	fmt.Printf("  Hostname:       %s\n", result.Hostname)
	if result.Platform != "" {
		fmt.Printf("  Platform:       %s\n", result.Platform)
	}
	if result.Connected {
		color.Green("  Connection:     ✓ connected (ws)")
	} else {
		color.Red("  Connection:     ✗ disconnected")
	}
	fmt.Printf("  Agent PID:      %d\n", result.AgentPID)
	fmt.Printf("  Agent Version:  %s\n", result.AgentVersion)
	fmt.Printf("  Running Tasks:  %d\n", result.RunningCommands)
	if result.LastHeartbeat > 0 {
		fmt.Printf("  Last Seen:      %s\n", formatRelativeTime(result.LastHeartbeat))
	}
	return nil
}

func runAgentDeploy(agentID string) error {
	fmt.Printf("正在部署 agent '%s' ...\n", agentID)
	result, err := apiClient.AgentDeploy(agentID, agentDeployTimeout)
	if err != nil {
		return err
	}
	if result.Success {
		color.Green("✓ Agent '%s' 部署成功", result.AgentID)
	} else {
		color.Red("✗ Agent '%s' 部署失败: %s", result.AgentID, result.Error)
		os.Exit(1)
	}
	return nil
}

func runAgentExec(agentID string, cmdArgs []string) error {
	if len(cmdArgs) == 0 {
		return fmt.Errorf("缺少命令参数")
	}
	command := strings.Join(cmdArgs, " ")

	result, err := apiClient.AgentExec(agentID, &models.AgentExecRequest{
		Command: command,
		Timeout: agentExecTimeout,
		Cwd:     agentExecCwd,
	})
	if err != nil {
		return err
	}

	if result.Stdout != "" {
		fmt.Print(result.Stdout)
	}
	if result.Stderr != "" {
		color.Red("%s", result.Stderr)
	}

	fmt.Printf("\n───── exec result ─────\n")
	fmt.Printf("  Agent:       %s\n", result.AgentID)
	if result.ExitCode == 0 {
		color.Green("  Exit Code:   %d", result.ExitCode)
	} else {
		color.Red("  Exit Code:   %d", result.ExitCode)
	}
	fmt.Printf("  Duration:    %dms\n", result.DurationMs)
	if result.Error != "" {
		color.Red("  Error:       %s", result.Error)
	}

	if result.ExitCode != 0 {
		os.Exit(result.ExitCode)
	}
	return nil
}

func printSingleResult(r *models.AgentCheckResult) {
	if r.Status == "connected" || r.Status == "ready" {
		color.Green("✓ %s (%s:%d) — %s in %dms", r.AgentID, r.Host, r.Port, r.Status, r.LatencyMs)
	} else {
		color.Red("✗ %s (%s:%d) — %s after %dms", r.AgentID, r.Host, r.Port, r.Status, r.LatencyMs)
	}
	fmt.Printf("  Type:     %s\n", r.Type)
	if r.System != "" || r.Arch != "" {
		fmt.Printf("  System:   %s\n", orUnknown(r.System))
		fmt.Printf("  Arch:     %s\n", orUnknown(r.Arch))
	}
	if r.Platform != "" {
		fmt.Printf("  Platform: %s\n", r.Platform)
	}
	fmt.Printf("  File:     %s\n", r.SourceFile)
	if r.Error != "" {
		color.Red("  Error:    %s\n", r.Error)
	}
}

func printCheckResultsGrouped(results []models.AgentCheckResult, summary *models.AgentCheckSummary) {
	groups := groupByFile(results)

	files := make([]string, 0, len(groups))
	for f := range groups {
		files = append(files, f)
	}
	sort.Strings(files)

	for _, file := range files {
		agents := groups[file]
		sort.Slice(agents, func(i, j int) bool {
			return agents[i].AgentID < agents[j].AgentID
		})

		color.Cyan("───── %s ─────", file)
		table := tablewriter.NewWriter(os.Stdout)
		table.SetHeader([]string{"Agent", "Host:Port", "Type", "System", "Arch", "Status", "Latency"})
		table.SetBorder(false)
		table.SetColumnSeparator(" ")
		table.SetAutoWrapText(false)

		for _, a := range agents {
			statusDisplay := fmt.Sprintf("✓ %s", a.Status)
			statusColor := color.New(color.FgGreen).SprintFunc()
			if a.Status == "failed" || a.Status == "disconnected" {
				statusDisplay = fmt.Sprintf("✗ %s", a.Status)
				statusColor = color.New(color.FgRed).SprintFunc()
			}
			hostPort := fmt.Sprintf("%s:%d", a.Host, a.Port)
			if a.Host == "" || a.Host == "localhost" {
				hostPort = "local"
			}
			latency := fmt.Sprintf("%dms", a.LatencyMs)
			table.Append([]string{
				a.AgentID,
				hostPort,
				truncateType(a.Type, 18),
				orUnknown(a.System),
				orUnknown(a.Arch),
				statusColor(statusDisplay),
				latency,
			})
		}
		table.Render()
		fmt.Println()
	}

	summaryColor := color.New(color.FgGreen).SprintFunc()
	if summary.Failed > 0 {
		summaryColor = color.New(color.FgYellow).SprintFunc()
	}
	fmt.Printf("Total: %s\n", summaryColor(
		fmt.Sprintf("%d agents — %d connected, %d failed",
			summary.Total,
			summary.Connected,
			summary.Failed,
		)))
}

func groupByFile(results []models.AgentCheckResult) map[string][]models.AgentCheckResult {
	groups := make(map[string][]models.AgentCheckResult)
	for _, r := range results {
		file := r.SourceFile
		groups[file] = append(groups[file], r)
	}
	return groups
}

func truncateType(t string, maxLen int) string {
	if len(t) > maxLen {
		return t[:maxLen-3] + "..."
	}
	return t + strings.Repeat(" ", maxLen-len(t))
}

// orUnknown 把空字符串显示为 "unknown"
func orUnknown(s string) string {
	if s == "" {
		return "unknown"
	}
	return s
}

func formatRelativeTime(timestamp float64) string {
	now := time.Now()
	t := time.Unix(int64(timestamp), int64((timestamp-float64(int64(timestamp)))*1e9))
	diff := now.Sub(t)

	if diff < 0 {
		return "刚刚"
	}

	seconds := int(diff.Seconds())
	if seconds < 5 {
		return "刚刚"
	}
	if seconds < 60 {
		return fmt.Sprintf("%d秒前", seconds)
	}

	minutes := int(diff.Minutes())
	if minutes < 60 {
		return fmt.Sprintf("%d分钟前", minutes)
	}

	hours := int(diff.Hours())
	if hours < 24 {
		return fmt.Sprintf("%d小时前", hours)
	}

	days := int(diff.Hours() / 24)
	return fmt.Sprintf("%d天前", days)
}

func init() {
	agentCmd.PersistentFlags().IntVarP(&agentTimeout, "timeout", "t", 5, "connect/check timeout in seconds")
	agentCmd.PersistentFlags().StringVarP(&agentFile, "file", "f", "", "filter by agent file name (without extension)")
	agentCmd.PersistentFlags().IntVarP(&agentDeployTimeout, "deploy-timeout", "", 30, "deployment timeout in seconds")
	agentCmd.PersistentFlags().StringVarP(&agentExecCwd, "cwd", "w", "", "working directory on agent (for exec)")
	agentCmd.PersistentFlags().IntVarP(&agentExecTimeout, "exec-timeout", "", 60, "command execution timeout in seconds")

	agentCmd.AddCommand(agentTryConnectCmd)
	agentCmd.AddCommand(agentCheckCmd)
	agentCmd.AddCommand(agentListCmd)
	agentCmd.AddCommand(agentStatusCmd)
	agentCmd.AddCommand(agentDeployCmd)
	agentCmd.AddCommand(agentExecCmd)
	RootCmd.AddCommand(agentCmd)
}

var agentListCmd = &cobra.Command{
	Use:   "list",
	Short: "列出所有连接的 agent",
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAgentList()
	},
}

var agentStatusCmd = &cobra.Command{
	Use:   "status [agent-id]",
	Short: "查看 agent 运行状态",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAgentStatus(args[0])
	},
}

var (
	agentDeployTimeout int
)

var agentExecCmd = &cobra.Command{
	Use:   "exec <agent-id> -- <command> [args...]",
	Short: "在指定 agent 上执行 shell 命令",
	Long: `通过 WebSocket 在指定 agent 上执行 shell 命令并返回 stdout/stderr 与退出码。

使用 -- 分隔命令参数以避免与 ppsctl 标志冲突。

示例:
  ppsctl agent exec auto-01 -- echo hello
  ppsctl agent exec auto-01 -t 30 -- ls -la /tmp
  ppsctl agent exec auto-01 -w /opt -- ./deploy.sh`,
	Args: cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAgentExec(args[0], args[1:])
	},
}

var agentDeployCmd = &cobra.Command{
	Use:   "deploy <agent-id>",
	Short: "部署 agent 到指定主机",
	Long:  "通过 Server API 触发 agent 自动部署（SSH bootstrap）到目标主机",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runAgentDeploy(args[0])
	},
}
