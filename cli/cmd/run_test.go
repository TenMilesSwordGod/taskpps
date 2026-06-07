package cmd

import (
	"testing"

	"github.com/spf13/pflag"
)

func TestRunCommandFlagShorthands(t *testing.T) {
	paramFlag := runCmd.Flags().Lookup("param")
	if paramFlag == nil {
		t.Fatal("run command should have --param flag")
	}
	if paramFlag.Shorthand != "p" {
		t.Errorf("--param shorthand should be 'p', got %q", paramFlag.Shorthand)
	}

	projectFlag := RootCmd.PersistentFlags().Lookup("project")
	if projectFlag == nil {
		t.Fatal("root command should have --project persistent flag")
	}
	if projectFlag.Shorthand != "P" {
		t.Errorf("--project shorthand should be 'P', got %q", projectFlag.Shorthand)
	}
}

func TestNoShorthandConflicts(t *testing.T) {
	shorthands := make(map[rune]string)

	checkShorthand := func(name string, shorthand string) {
		if shorthand == "" {
			return
		}
		r := rune(shorthand[0])
		if existing, ok := shorthands[r]; ok {
			t.Errorf("shorthand conflict: -%s used by both --%s and --%s", shorthand, existing, name)
		}
		shorthands[r] = name
	}

	RootCmd.PersistentFlags().VisitAll(func(f *pflag.Flag) {
		checkShorthand(f.Name, f.Shorthand)
	})

	runCmd.Flags().VisitAll(func(f *pflag.Flag) {
		checkShorthand(f.Name, f.Shorthand)
	})
}

func TestRunCommandRegistration(t *testing.T) {
	found := false
	for _, cmd := range RootCmd.Commands() {
		if cmd.Name() == "run" {
			found = true
			break
		}
	}
	if !found {
		t.Error("RootCmd should have run command registered")
	}
}

func TestRunCommandArgs(t *testing.T) {
	if runCmd.Args == nil {
		t.Error("run command should require exactly one argument")
	}
}

func TestRunCommandParamFlagType(t *testing.T) {
	flag := runCmd.Flags().Lookup("param")
	if flag == nil {
		t.Fatal("run command should have --param flag")
	}
	if flag.Value.Type() != "stringArray" {
		t.Errorf("--param flag should be stringArray, got %s", flag.Value.Type())
	}
}

func TestRunCommandDetachFlag(t *testing.T) {
	flag := runCmd.Flags().Lookup("detach")
	if flag == nil {
		t.Fatal("run command should have --detach flag")
	}
	if flag.DefValue != "false" {
		t.Errorf("--detach default should be false, got %s", flag.DefValue)
	}
}
