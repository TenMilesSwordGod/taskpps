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
	agentTimeout int
	agentFile    string
)

var agentCmd = &cobra.Command{
	Use:   "agent",
	Short: "Manage and check agent connections",
	Long: `Manage agents and check their connectivity.

Subcommands:
  try-connect  Test connectivity to a specific agent
  check        Check all agent connections, grouped by file`,
	Run: func(cmd *cobra.Command, args []string) {
		cmd.Help()
	},
}

var agentTryConnectCmd = &cobra.Command{
	Use:   "try-connect <agent-id>",
	Short: "Test connectivity to a specific agent",
	Long: `Attempt a TCP connection to the specified agent and report the result.

Example:
  ppsctl agent try-connect prod-server
  ppsctl agent try-connect prod-server --timeout 10`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		agentID := args[0]

		result, err := apiClient.TryConnect(agentID, agentTimeout)
		if err != nil {
			return err
		}

		printSingleResult(result)
		if result.Status == "failed" {
			os.Exit(1)
		}
		return nil
	},
}

var agentCheckCmd = &cobra.Command{
	Use:   "check [agent-id]",
	Short: "Check agent connections with live progress",
	Long: `Check connectivity of one or all agents in real-time, grouped by agent file.

Results are streamed live as each agent is checked. A grouped summary table
is shown after all checks complete.
Falls back to batch mode if the server does not support streaming.

Examples:
  ppsctl agent check                     Check all agents
  ppsctl agent check prod-server         Check a specific agent
  ppsctl agent check --file staging      Check agents in staging.yaml only`,
	Args: cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		var agentID string
		if len(args) > 0 {
			agentID = args[0]
		}

		var results []models.AgentCheckResult
		var cnt int

		summary, err := apiClient.CheckAgentsStream(agentID, agentFile, agentTimeout, func(r models.AgentCheckResult) {
			results = append(results, r)
			cnt++
			fmt.Printf("\r\033[K")
			if r.Status == "failed" {
				color.Red("[%d] ✗ %s (%s:%d) — %s", cnt, r.AgentID, r.Host, r.Port, r.Status)
				if r.Error != "" {
					fmt.Printf(": %s", r.Error)
				}
				fmt.Println()
			} else {
				color.Green("[%d] ✓ %s (%s:%d) — %s in %dms", cnt, r.AgentID, r.Host, r.Port, r.Status, r.LatencyMs)
				fmt.Println()
			}
		})

		if err != nil && strings.Contains(err.Error(), "404") {
			response, err2 := apiClient.CheckAgents(agentID, agentFile, agentTimeout)
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
	},
}

func printSingleResult(r *models.AgentCheckResult) {
	if r.Status == "connected" || r.Status == "ready" {
		color.Green("✓ %s (%s:%d) — %s in %dms", r.AgentID, r.Host, r.Port, r.Status, r.LatencyMs)
	} else {
		color.Red("✗ %s (%s:%d) — %s after %dms", r.AgentID, r.Host, r.Port, r.Status, r.LatencyMs)
	}
	fmt.Printf("  Type:     %s\n", r.Type)
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
		table.SetHeader([]string{"Agent", "Host:Port", "Type", "Status", "Latency"})
		table.SetBorder(false)
		table.SetColumnSeparator(" ")
		table.SetAutoWrapText(false)

		for _, a := range agents {
			statusDisplay := fmt.Sprintf("✓ %s", a.Status)
			statusColor := color.New(color.FgGreen).SprintFunc()
			if a.Status == "failed" {
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
	agentTryConnectCmd.Flags().IntVarP(&agentTimeout, "timeout", "t", 5, "connection timeout in seconds")
	agentCheckCmd.Flags().IntVarP(&agentTimeout, "timeout", "t", 5, "connection timeout in seconds")
	agentCheckCmd.Flags().StringVarP(&agentFile, "file", "f", "", "filter by agent file name (without extension)")

	agentDeployCmd.Flags().IntVarP(&agentDeployTimeout, "timeout", "t", 30, "deployment timeout in seconds")

	agentCmd.AddCommand(agentTryConnectCmd)
	agentCmd.AddCommand(agentCheckCmd)
	agentCmd.AddCommand(agentListCmd)
	agentCmd.AddCommand(agentStatusCmd)
	agentCmd.AddCommand(agentDeployCmd)
	RootCmd.AddCommand(agentCmd)
}

var agentListCmd = &cobra.Command{
	Use:   "list",
	Short: "列出所有连接的 agent",
	RunE: func(cmd *cobra.Command, args []string) error {
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
		table.SetHeader([]string{"Agent ID", "Hostname", "Version", "PID", "Tasks"})
		table.SetBorder(false)
		table.SetColumnSeparator(" ")
		for _, a := range agents {
			status := "✓ connected"
			statusColor := color.New(color.FgGreen).SprintFunc()
			table.Append([]string{
				a.AgentID,
				a.Hostname,
				a.AgentVersion,
				fmt.Sprintf("%d", a.AgentPID),
				fmt.Sprintf("%d", a.RunningCommands),
			})
			_ = statusColor(status)
		}
		table.Render()
		fmt.Printf("\nTotal: %d agents connected\n", len(agents))
		return nil
	},
}

var agentStatusCmd = &cobra.Command{
	Use:   "status [agent-id]",
	Short: "查看 agent 运行状态",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		agentID := args[0]
		result, err := apiClient.AgentStatus(agentID)
		if err != nil {
			return err
		}

		fmt.Printf("───── Agent Status ─────\n")
		fmt.Printf("  Agent ID:       %s\n", result.AgentID)
		fmt.Printf("  Hostname:       %s\n", result.Hostname)
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
	},
}

var (
	agentDeployTimeout int
)

var agentDeployCmd = &cobra.Command{
	Use:   "deploy <agent-id>",
	Short: "部署 agent 到指定主机",
	Long:  "通过 Server API 触发 agent 自动部署（SSH bootstrap）到目标主机",
	Args:  cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		agentID := args[0]
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
	},
}
