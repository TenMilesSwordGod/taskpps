package testutil

import (
	"flag"
	"os"
	"path/filepath"
	"regexp"
	"testing"
)

var ansiRegex = regexp.MustCompile(`\x1b\[[0-9;]*[a-zA-Z]`)

var updateGolden = flag.Bool("update", false, "update golden files")

func StripANSI(s string) string {
	return ansiRegex.ReplaceAllString(s, "")
}

func AssertGolden(t *testing.T, got string, goldenPath string) {
	t.Helper()

	got = StripANSI(got)

	goldenFile := filepath.Join("testdata", goldenPath)

	if *updateGolden {
		dir := filepath.Dir(goldenFile)
		if err := os.MkdirAll(dir, 0755); err != nil {
			t.Fatalf("failed to create golden dir: %v", err)
		}
		if err := os.WriteFile(goldenFile, []byte(got), 0644); err != nil {
			t.Fatalf("failed to write golden file: %v", err)
		}
		return
	}

	expected, err := os.ReadFile(goldenFile)
	if err != nil {
		t.Fatalf("failed to read golden file %s: %v\nRun with -update to create it", goldenFile, err)
	}

	expectedStr := string(expected)
	if got != expectedStr {
		t.Errorf("golden file mismatch for %s\n--- EXPECTED ---\n%s\n--- GOT ---\n%s", goldenPath, expectedStr, got)
	}
}
