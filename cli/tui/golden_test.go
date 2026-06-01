package tui

import (
	"testing"

	"github.com/charmbracelet/lipgloss"
	"github.com/muesli/termenv"
	"github.com/taskpps/ppsctl/models"
	testutil "github.com/taskpps/ppsctl/tui/testutil"
)

func initGoldenTest() {
	lipgloss.SetColorProfile(termenv.Ascii)
}

func TestGoldenInitLoading(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	view := m.View()
	testutil.AssertGolden(t, view, "init_loading.golden")
}

func TestGoldenEmptyRuns(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = nil
	m.runList.SetRuns(nil)

	view := m.View()
	testutil.AssertGolden(t, view, "empty_runs.golden")
}

func TestGoldenNormalRunsFocusLeft(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.state.FocusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "normal_runs_focus_left.golden")
}

func TestGoldenRunDetailExpanded(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.ExpandAll()

	view := m.View()
	testutil.AssertGolden(t, view, "run_detail_expanded.golden")
}

func TestGoldenLogViewer(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.logViewer.SetContent("[build] Building project...\n[build] Compiling main.go\n[test] Running tests...\n[test] All tests passed")

	view := m.View()
	testutil.AssertGolden(t, view, "log_viewer.golden")
}

func TestGoldenNarrowTerminal(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 80
	m.state.Height = 25
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.state.FocusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "narrow_terminal.golden")
}

func TestGoldenWideTerminal(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 200
	m.state.Height = 50
	m.resizeComponents()

	runs := testutil.MakeMixedPipelineRuns()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(2)
	m.runDetail.SetRun(&runs[2])
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail

	view := m.View()
	testutil.AssertGolden(t, view, "wide_terminal.golden")
}

func TestGoldenErrorState(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	runs := []models.Run{{ID: "err-run", PipelineName: "failing", Status: models.RunStatusFailed}}
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.state.ErrorMsg = "connection refused: server unreachable"
	m.state.FocusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "error_state.golden")
}

func TestGoldenMixedPipelines(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	runs := testutil.MakeMixedPipelineRuns()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.state.FocusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "mixed_pipelines.golden")
}

func TestGoldenAllTaskStatuses(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	run := testutil.MakeTestRunAllStatuses()
	m.state.Runs = []models.Run{run}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&run)
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.ExpandAll()

	view := m.View()
	testutil.AssertGolden(t, view, "all_task_statuses.golden")
}

func TestGoldenQuitting(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.state.Quit = true
	view := m.View()
	testutil.AssertGolden(t, view, "quitting.golden")
}
