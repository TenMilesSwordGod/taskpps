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
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()
	m.runs = nil
	m.runList.SetRuns(nil)

	view := m.View()
	testutil.AssertGolden(t, view, "empty_runs.golden")
}

func TestGoldenNormalRunsFocusLeft(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.runs = runs
	m.runList.SetRuns(runs)
	m.focusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "normal_runs_focus_left.golden")
}

func TestGoldenRunDetailExpanded(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail
	m.runDetail.ExpandAll()

	view := m.View()
	testutil.AssertGolden(t, view, "run_detail_expanded.golden")
}

func TestGoldenLogViewer(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&runs[0])
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabLogs
	m.logViewer.SetContent("[build] Building project...\n[build] Compiling main.go\n[test] Running tests...\n[test] All tests passed")

	view := m.View()
	testutil.AssertGolden(t, view, "log_viewer.golden")
}

func TestGoldenNarrowTerminal(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 80
	m.height = 25
	m.resizeComponents()

	runs := testutil.MakeTestRuns()
	m.runs = runs
	m.runList.SetRuns(runs)
	m.focusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "narrow_terminal.golden")
}

func TestGoldenWideTerminal(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 200
	m.height = 50
	m.resizeComponents()

	runs := testutil.MakeMixedPipelineRuns()
	m.runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(2)
	m.runDetail.SetRun(&runs[2])
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail

	view := m.View()
	testutil.AssertGolden(t, view, "wide_terminal.golden")
}

func TestGoldenErrorState(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := []models.Run{{ID: "err-run", PipelineName: "failing", Status: models.RunStatusFailed}}
	m.runs = runs
	m.runList.SetRuns(runs)
	m.errMsg = "connection refused: server unreachable"
	m.focusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "error_state.golden")
}

func TestGoldenMixedPipelines(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	runs := testutil.MakeMixedPipelineRuns()
	m.runs = runs
	m.runList.SetRuns(runs)
	m.focusedPanel = FocusRunList

	view := m.View()
	testutil.AssertGolden(t, view, "mixed_pipelines.golden")
}

func TestGoldenAllTaskStatuses(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.ready = true
	m.width = 120
	m.height = 40
	m.resizeComponents()

	run := testutil.MakeTestRunAllStatuses()
	m.runs = []models.Run{run}
	m.runList.SetRuns(m.runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&run)
	m.focusedPanel = FocusRightPanel
	m.rightTab = TabDetail
	m.runDetail.ExpandAll()

	view := m.View()
	testutil.AssertGolden(t, view, "all_task_statuses.golden")
}

func TestGoldenQuitting(t *testing.T) {
	initGoldenTest()
	m := makeTestModel()
	m.quit = true
	view := m.View()
	testutil.AssertGolden(t, view, "quitting.golden")
}
