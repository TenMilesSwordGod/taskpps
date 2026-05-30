package cmd

import (
	"testing"

	"github.com/taskpps/ppsctl/models"
)

func TestGroupByFile(t *testing.T) {
	results := []models.AgentCheckResult{
		{AgentID: "agent-a", SourceFile: "agents/staging.yaml", Host: "10.0.0.1", Port: 22, Status: "connected"},
		{AgentID: "agent-b", SourceFile: "agents/staging.yaml", Host: "10.0.0.2", Port: 22, Status: "connected"},
		{AgentID: "agent-c", SourceFile: "agents/prod.yaml", Host: "10.0.0.3", Port: 22, Status: "failed"},
	}

	groups := groupByFile(results)

	if len(groups) != 2 {
		t.Errorf("expected 2 groups, got %d", len(groups))
	}

	stagingAgents := groups["agents/staging.yaml"]
	if len(stagingAgents) != 2 {
		t.Errorf("expected 2 agents in staging, got %d", len(stagingAgents))
	}

	prodAgents := groups["agents/prod.yaml"]
	if len(prodAgents) != 1 {
		t.Errorf("expected 1 agent in prod, got %d", len(prodAgents))
	}
}

func TestGroupByFileSingleGroup(t *testing.T) {
	results := []models.AgentCheckResult{
		{AgentID: "agent-x", SourceFile: "agents/ssh.yaml", Host: "10.0.0.1", Port: 22, Status: "connected"},
	}

	groups := groupByFile(results)

	if len(groups) != 1 {
		t.Errorf("expected 1 group, got %d", len(groups))
	}
}

func TestGroupByFileEmpty(t *testing.T) {
	results := []models.AgentCheckResult{}

	groups := groupByFile(results)

	if len(groups) != 0 {
		t.Errorf("expected 0 groups, got %d", len(groups))
	}
}

func TestTruncateType(t *testing.T) {
	testCases := []struct {
		name   string
		input  string
		maxLen int
	}{
		{"short", "local", 18},
		{"exact18", "exactly-18-chars-x", 18},
		{"truncate", "this-is-longer-than-18", 18},
		{"pad", "ssh-key", 18},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := truncateType(tc.input, tc.maxLen)
			if len(result) != tc.maxLen {
				t.Errorf("truncateType(%q, %d) len = %d, want %d", tc.input, tc.maxLen, len(result), tc.maxLen)
			}
			if tc.name == "truncate" {
				if !(len(tc.input) > tc.maxLen && result[len(result)-3:] == "...") {
					t.Errorf("truncateType(%q, %d) should truncate with '...': got %q", tc.input, tc.maxLen, result)
				}
			} else {
				if tc.input != result[:len(tc.input)] {
					t.Errorf("truncateType(%q, %d) prefix mismatch: got %q", tc.input, tc.maxLen, result)
				}
			}
		})
	}
}

func TestAgentCommandRegistration(t *testing.T) {
	found := false
	for _, cmd := range agentCmd.Commands() {
		if cmd.Name() == "try-connect" {
			found = true
			break
		}
	}
	if !found {
		t.Error("agent command should have try-connect subcommand")
	}

	found = false
	for _, cmd := range agentCmd.Commands() {
		if cmd.Name() == "check" {
			found = true
			break
		}
	}
	if !found {
		t.Error("agent command should have check subcommand")
	}
}

func TestAgentCommandRootRegistration(t *testing.T) {
	found := false
	for _, cmd := range RootCmd.Commands() {
		if cmd.Name() == "agent" {
			found = true
			break
		}
	}
	if !found {
		t.Error("RootCmd should have agent command registered")
	}
}

func TestAgentTryConnectRequiresArg(t *testing.T) {
	if agentTryConnectCmd.Args == nil {
		t.Error("try-connect should require an argument")
	}
}

func TestAgentCheckArgs(t *testing.T) {
	if agentCheckCmd.Args == nil {
		t.Error("check should accept optional argument")
	}
}

func TestAgentTimeoutFlag(t *testing.T) {
	flag := agentTryConnectCmd.Flags().Lookup("timeout")
	if flag == nil {
		t.Error("try-connect should have --timeout flag")
	}
	if flag.DefValue != "5" {
		t.Errorf("default timeout should be 5, got %s", flag.DefValue)
	}

	flag = agentCheckCmd.Flags().Lookup("timeout")
	if flag == nil {
		t.Error("check should have --timeout flag")
	}

	flag = agentCheckCmd.Flags().Lookup("file")
	if flag == nil {
		t.Error("check should have --file flag")
	}
}