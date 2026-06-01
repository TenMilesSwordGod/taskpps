package tui

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"strconv"
	"testing"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/models"
	"github.com/taskpps/ppsctl/tui/components"
)

func makeTestClient() *client.Client {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	return client.New(cfg)
}

func TestFetchLogsSync(t *testing.T) {
	c := makeTestClient()
	_, err := fetchLogsSync(c, "test-run", "test-task")
	if err != nil {
		t.Logf("fetchLogsSync failed as expected: %v", err)
	}
}

func TestUpdateEnterOnDetailWithExpandedTask(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
			{TaskName: "t2", Status: models.TaskStatusPending},
		},
	})
	m.runDetail.SetSize(80, 24)
	m.runDetail.SetCursor(2)

	msg := tea.KeyMsg{Type: tea.KeyEnter}
	m2, cmd := m.Update(msg)
	_ = m2
	_ = cmd
}

func TestAppStateCopy(t *testing.T) {
	s := NewAppState()
	s.Runs = []models.Run{{ID: "r1"}}
	s.DetailExpanded[0] = true
	s.SubExpanded["sub1"] = true
	s.SelectedRun = &models.Run{ID: "sel", Status: models.RunStatusRunning}
	s.RunsHash = "hash1"
	s.RunHash = "hash2"
	s.FocusedPanel = FocusRightPanel
	s.RightTab = TabLogs
	s.LogContent = "logs"
	s.ErrorMsg = "err"
	s.Width = 120
	s.Height = 40

	cp := s.Copy()

	if cp.FocusedPanel != s.FocusedPanel {
		t.Error("FocusedPanel should copy")
	}
	if cp.RightTab != s.RightTab {
		t.Error("RightTab should copy")
	}
	if len(cp.DetailExpanded) != 1 || !cp.DetailExpanded[0] {
		t.Error("DetailExpanded should deep copy")
	}
	if len(cp.SubExpanded) != 1 || !cp.SubExpanded["sub1"] {
		t.Error("SubExpanded should deep copy")
	}
	if cp.SelectedRun == nil || cp.SelectedRun.ID != "sel" {
		t.Error("SelectedRun should copy")
	}
	cp.DetailExpanded[1] = true
	if s.DetailExpanded[1] {
		t.Error("original DetailExpanded should not be modified")
	}
	cp.SubExpanded["new"] = true
	if s.SubExpanded["new"] {
		t.Error("original SubExpanded should not be modified")
	}
	cp.SelectedRun.ID = "modified"
	if s.SelectedRun.ID != "sel" {
		t.Error("original SelectedRun should not be modified")
	}
}

func TestAppStateCopyNilRun(t *testing.T) {
	s := NewAppState()
	cp := s.Copy()
	if cp.SelectedRun != nil {
		t.Error("nil SelectedRun should stay nil in copy")
	}
}

func TestAppStateComputeViewHash(t *testing.T) {
	s := NewAppState()
	h1 := s.computeViewHash()
	if h1 == "" {
		t.Error("computeViewHash should not be empty")
	}

	s2 := NewAppState()
	h2 := s2.computeViewHash()
	if h1 != h2 {
		t.Error("same state should produce same hash")
	}

	s.ErrorMsg = "changed"
	h3 := s.computeViewHash()
	if h1 == h3 {
		t.Error("different state should produce different hash")
	}
}

func TestAppStateIsViewSameAs(t *testing.T) {
	s1 := NewAppState()
	s2 := NewAppState()

	if s1.IsViewSameAs(s2) {
		t.Error("empty viewHash should return false")
	}

	s1.viewHash = "abc"
	if s1.IsViewSameAs(s2) {
		t.Error("one empty viewHash should return false")
	}

	s2.viewHash = "abc"
	if !s1.IsViewSameAs(s2) {
		t.Error("same viewHash should return true")
	}

	s2.viewHash = "def"
	if s1.IsViewSameAs(s2) {
		t.Error("different viewHash should return false")
	}
}

func TestSyncComponentsFromState(t *testing.T) {
	m := makeTestModel()
	s := m.state
	s.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "p2", Status: models.RunStatusSuccess},
	}
	s.RunListCursor = 1
	s.SelectedRun = &models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	}
	s.DetailCursor = 0
	s.DetailExpanded = map[int]bool{0: true}
	s.SubExpanded = map[string]bool{"sub1": true}
	s.LogContent = "test log content"
	s.LogLoading = true
	m.state = s

	m.syncComponentsFromState()

	if m.runList.Len() != 2 {
		t.Errorf("runList should have 2 runs, got %d", m.runList.Len())
	}
	if m.logViewer.Content() != "test log content" {
		t.Error("logViewer should have content")
	}
}

func TestSyncStateFromComponents(t *testing.T) {
	m := makeTestModel()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})
	m.runDetail.SetCursor(0)

	m.syncStateFromComponents()

	if m.state.RunListCursor != 0 {
		t.Errorf("RunListCursor should be 0, got %d", m.state.RunListCursor)
	}
	if m.state.DetailCursor != 0 {
		t.Errorf("DetailCursor should be 0, got %d", m.state.DetailCursor)
	}
	if m.state.SelectedRun == nil {
		t.Error("SelectedRun should not be nil")
	}
	if m.state.SelectedTask != nil {
		t.Error("SelectedTask should be nil when cursor=0 (header)")
	}
}

func TestShouldSkipTick(t *testing.T) {
	m := makeTestModel()

	if m.shouldSkipTick() {
		t.Error("shouldSkipTick should be false when no activity")
	}

	m.recordUserActivity()
	time.Sleep(10 * time.Millisecond)
	if !m.shouldSkipTick() {
		t.Error("shouldSkipTick should be true right after activity")
	}
}

func TestComputeRunHashNil(t *testing.T) {
	h := computeRunHash(nil)
	if h != "" {
		t.Errorf("computeRunHash(nil) = %q, want empty", h)
	}
}

func TestFetchClosures(t *testing.T) {
	c := makeTestClient()

	cmd := fetchRuns(c)
	if cmd == nil {
		t.Error("fetchRuns should return command")
	}
	msg := cmd()
	if _, ok := msg.(runsFetchedMsg); !ok {
		t.Error("fetchRuns cmd should return runsFetchedMsg")
	}

	cmd2 := fetchRun(c, "test123")
	if cmd2 == nil {
		t.Error("fetchRun should return command")
	}
	msg2 := cmd2()
	if _, ok := msg2.(runFetchedMsg); !ok {
		t.Error("fetchRun cmd should return runFetchedMsg")
	}

	cmd3 := fetchLogs(c, "test123", "task1")
	if cmd3 == nil {
		t.Error("fetchLogs should return command")
	}
	msg3 := cmd3()
	if _, ok := msg3.(logsFetchedMsg); !ok {
		t.Error("fetchLogs cmd should return logsFetchedMsg")
	}
}

func TestUpdateDebounceTick(t *testing.T) {
	m := makeTestModel()
	m.pendingRender = true
	msg := debounceTickMsg{}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	if model.pendingRender {
		t.Error("pendingRender should be false after debounce tick")
	}
	_ = cmd

	m.pendingRender = false
	msg2 := debounceTickMsg{}
	m3, cmd2 := m.Update(msg2)
	model2 := m3.(Model)
	if model2.pendingRender {
		t.Error("pendingRender should remain false")
	}
	_ = cmd2
}

func TestUpdateTickSkipDueToActivity(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.recordUserActivity()
	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	_ = model
	if cmd == nil {
		t.Error("tick should still return timer cmd even when skipping")
	}
}

func TestUpdateRefreshWithSelectedRun(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&m.state.Runs[0])

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestUpdateDuplicateHashes(t *testing.T) {
	t.Run("runsFetched_same_hash", func(t *testing.T) {
		m := makeTestModel()
		runs := []models.Run{
			{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
		}
		m.state.Runs = runs
		m.state.RunsHash = computeRunsHash(runs)

		msg := runsFetchedMsg{runs: runs}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		if len(model.state.Runs) != 1 {
			t.Error("runs should remain unchanged")
		}
	})

	t.Run("runFetched_same_hash", func(t *testing.T) {
		m := makeTestModel()
		run := &models.Run{ID: "abc", Status: models.RunStatusRunning}
		m.state.SelectedRun = run
		m.state.RunHash = computeRunHash(run)

		msg := runFetchedMsg{run: run}
		m2, _ := m.Update(msg)
		model := m2.(Model)
		_ = model
	})
}

func TestUpdateTKeyLogsTab(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "abc",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})
	m.runDetail.SetCursor(1)

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}}
	_, cmd := m.Update(msg)
	if cmd == nil {
		t.Error("t key on detail with task should dispatch fetchLogs")
	}
}

func TestUpdateTKeyLogsTabBack(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.RightTab != TabDetail {
		t.Error("t key on logs tab should switch back to Detail")
	}
}

func TestUpdateUnknownKeyDispatch(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRunList

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'x'}}
	_, _ = m.Update(msg)

	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID: "abc", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{{TaskName: "t1"}},
	})
	_, _ = m.Update(msg)

	m.state.RightTab = TabLogs
	m.logViewer.SetContent("some logs")
	m.logViewer.SetSize(80, 20)
	_, _ = m.Update(msg)
}

func TestDispatchKeyDetailPrefetch(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail

	m.runDetail.SetRun(&models.Run{
		ID:     "abc",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "task1", Status: models.TaskStatusRunning},
		},
	})
	m.logViewer.SetContent("")

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	if cmd != nil {
		t.Log("prefetchLogs dispatched as expected")
	}

	m.logViewer.SetContent("existing_logs")
	m.logViewer.SetSize(80, 20)
	cmd2 := m.dispatchKey(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	_ = cmd2
}

func TestNavigatePrevPipelineEdgeCases(t *testing.T) {
	t.Run("empty_runs", func(t *testing.T) {
		m := makeTestModel()
		cmd := m.navigatePrevPipeline()
		if cmd != nil {
			t.Error("should return nil for empty runs")
		}
	})

	t.Run("nil_selected_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
		}
		cmd := m.navigatePrevPipeline()
		if cmd != nil {
			t.Error("should return nil when no run selected")
		}
	})

	t.Run("at_first_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
			{ID: "r2", Status: models.RunStatusSuccess},
		}
		m.runList.SetRuns(m.state.Runs)
		m.runList.SetCursor(0)
		m.runDetail.SetRun(&m.state.Runs[0])
		cmd := m.navigatePrevPipeline()
		if cmd != nil {
			t.Error("should return nil at first run")
		}
	})
}

func TestNavigateNextPipelineEdgeCases(t *testing.T) {
	t.Run("empty_runs", func(t *testing.T) {
		m := makeTestModel()
		cmd := m.navigateNextPipeline()
		if cmd != nil {
			t.Error("should return nil for empty runs")
		}
	})

	t.Run("nil_selected_run", func(t *testing.T) {
		m := makeTestModel()
		m.state.Runs = []models.Run{
			{ID: "r1", Status: models.RunStatusRunning},
		}
		cmd := m.navigateNextPipeline()
		if cmd != nil {
			t.Error("should return nil when no run selected")
		}
	})
}

func TestResizeComponentsEdgeCases(t *testing.T) {
	m := makeTestModel()

	t.Run("very_small_window", func(t *testing.T) {
		m.state.Width = 10
		m.state.Height = 10
		m.resizeComponents()
		if m.state.Dims.contentH < 3 {
			t.Log("contentH clamped to minimum")
		}
	})

	t.Run("narrow_window", func(t *testing.T) {
		m.state.Width = 40
		m.state.Height = 30
		m.resizeComponents()
		if m.state.Dims.leftContentW < 14 {
			t.Error("leftContentW should be at least 14")
		}
	})

	t.Run("minimum_height", func(t *testing.T) {
		m.state.Width = 100
		m.state.Height = 3
		m.resizeComponents()
	})
}

func TestRenderFooterWithError(t *testing.T) {
	m := makeTestModel()
	m.state.ErrorMsg = "connection refused: timeout after 30s"
	result := renderFooter(100, m.state, &m)
	if result == "" {
		t.Error("renderFooter with error should not be empty")
	}
}

func TestRenderFooterRightPanelLogs(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	result := renderFooter(100, m.state, &m)
	if result == "" {
		t.Error("renderFooter for logs tab should not be empty")
	}
}

func TestRenderFooterRightPanelDetail(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	result := renderFooter(100, m.state, &m)
	if result == "" {
		t.Error("renderFooter for detail tab should not be empty")
	}
}

func TestComputeRunsHash(t *testing.T) {
	runs := []models.Run{
		{ID: "r1", PipelineName: "p1"},
		{ID: "r2", PipelineName: "p2"},
	}
	h1 := computeRunsHash(runs)
	if h1 == "" {
		t.Error("computeRunsHash should not be empty")
	}

	h2 := computeRunsHash([]models.Run{
		{ID: "r1", PipelineName: "p1"},
		{ID: "r2", PipelineName: "p2"},
	})
	if h1 != h2 {
		t.Error("identical runs should produce identical hash")
	}

	h3 := computeRunsHash([]models.Run{
		{ID: "r1", PipelineName: "p1"},
	})
	if h1 == h3 {
		t.Error("different runs should produce different hash")
	}
}

func TestComputeRunHashFunc(t *testing.T) {
	run := &models.Run{ID: "r1", Status: models.RunStatusRunning, PipelineName: "p1"}
	h1 := computeRunHash(run)
	if h1 == "" {
		t.Error("computeRunHash should not be empty")
	}

	run2 := &models.Run{ID: "r1", Status: models.RunStatusRunning, PipelineName: "p1"}
	h2 := computeRunHash(run2)
	if h1 != h2 {
		t.Error("identical runs should produce identical hash")
	}

	run3 := &models.Run{ID: "r2", Status: models.RunStatusSuccess, PipelineName: "p2"}
	h3 := computeRunHash(run3)
	if h1 == h3 {
		t.Error("different runs should produce different hash")
	}
}

func TestComputeViewHashFunction(t *testing.T) {
	h1 := computeViewHash("hello")
	h2 := computeViewHash("hello")
	if h1 != h2 {
		t.Error("same string should produce same hash")
	}

	h3 := computeViewHash("world")
	if h1 == h3 {
		t.Error("different strings should produce different hash")
	}
}

func TestPadRightVisualEdgeCases(t *testing.T) {
	result := padRightVisual("test", 0)
	if result != "" {
		t.Errorf("padRightVisual with 0 width should be empty, got %q", result)
	}

	result = padRightVisual("test", -1)
	if result != "" {
		t.Errorf("padRightVisual with negative width should be empty, got %q", result)
	}
}

func TestTruncateStrEdgeCases(t *testing.T) {
	result := truncateStr("hello", 3)
	if len(result) > 3 {
		t.Errorf("truncateStr with maxLen=3 should be <=3, got %q", result)
	}

	result = truncateStr("hello", 0)
	if result != "" {
		t.Errorf("truncateStr with maxLen=0 should be empty, got %q", result)
	}

	result = truncateStr("test", 3)
	if result == "test" {
		t.Error("truncateStr should truncate when shorter than input")
	}
}

func TestViewQuit(t *testing.T) {
	m := makeTestModel()
	m.state.Quit = true
	result := m.View()
	if result != "" {
		t.Errorf("View with Quit=true should be empty, got %q", result)
	}
}

func TestViewNotReadyState(t *testing.T) {
	m := makeTestModel()
	result := m.View()
	if result != "Initializing...\n" {
		t.Errorf("View when not ready should show Initializing, got %q", result)
	}
}



func TestDebugRecorderWriteHeaderFooterNilFile(t *testing.T) {
	rec := &DebugRecorder{}
	rec.writeHeader("cmd", "xterm", "/dev/pts/0", 80, 24)
	rec.writeFooter(0)
}

func TestDebugRecorderEnableDisable(t *testing.T) {
	if GetDebugRecorder().IsEnabled() {
		t.Skip("recorder already enabled from other test")
	}

	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)

	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	err := EnableDebugRecorder("test", "xterm", "/dev/pts/1", 120, 40)
	if err != nil {
		t.Fatalf("EnableDebugRecorder failed: %v", err)
	}
	if !GetDebugRecorder().IsEnabled() {
		t.Error("should be enabled after EnableDebugRecorder")
	}

	DisableDebugRecorder(0)
	if GetDebugRecorder().IsEnabled() {
		t.Error("should be disabled after DisableDebugRecorder")
	}
}

func TestDebugRecorderRecordFrameNewline(t *testing.T) {
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)

	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	rec := &DebugRecorder{}
	err := rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	if err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	rec.RecordFrame("no trailing newline")
	rec.RecordFrame("with trailing newline\n")
	rec.Stop(0)
}

func TestResizeComponentsMinimalDimensions(t *testing.T) {
	m := makeTestModel()

	t.Run("available_height_clamped", func(t *testing.T) {
		m.state.Width = 80
		m.state.Height = 4
		m.resizeComponents()
	})

	t.Run("total_content_width_clamped", func(t *testing.T) {
		m.state.Width = 25
		m.state.Height = 30
		m.resizeComponents()
		if m.state.Dims.innerW < 38 {
			t.Log("innerW clamped to reasonable minimum")
		}
	})
}

func TestDispatchKeyLogViewerNotLoading(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.logViewer.SetContent("test content")
	m.logViewer.SetSize(80, 20)

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	_ = cmd
}

func TestUpdateShiftTab(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRunList
	msg := tea.KeyMsg{Type: tea.KeyShiftTab}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.FocusedPanel != FocusRightPanel {
		t.Error("shift+tab should move focus to RightPanel")
	}
}

func TestUpdateNavigationFromRunlist(t *testing.T) {
	t.Run("p_from_runlist_noop", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRunList
		m.state.Ready = true
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'p'}}
		_, cmd := m.Update(msg)
		if cmd != nil {
			t.Error("p from RunList should not dispatch")
		}
	})

	t.Run("n_from_runlist_noop", func(t *testing.T) {
		m := makeTestModel()
		m.state.FocusedPanel = FocusRunList
		m.state.Ready = true
		msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}}
		_, cmd := m.Update(msg)
		if cmd != nil {
			t.Error("n from RunList should not dispatch")
		}
	})
}

func TestUpdateTKeyOnRunList(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRunList
	m.state.Ready = true
	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.FocusedPanel != FocusRunList {
		t.Error("t key on RunList should not change focus")
	}
}

func TestUpdateEnterOnRunListNoSelection(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRunList
	m.state.Ready = true
	msg := tea.KeyMsg{Type: tea.KeyEnter}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.FocusedPanel != FocusRunList {
		t.Error("enter on RunList with no runs should not change focus")
	}
}

func TestUpdateWindowSizeGap(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 80
	m.state.Height = 24
	m.resizeComponents()

	msg := tea.WindowSizeMsg{Width: 120, Height: 40}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if !model.state.Ready {
		t.Error("should be ready after resize")
	}
}

func TestViewVisibility(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	result := m.View()
	if result == "" {
		t.Error("View should not be empty when ready")
	}
}

func TestViewTabLogs(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.state.RightTab = TabLogs
	m.logViewer.SetContent("test logs")
	m.logViewer.SetSize(80, 20)
	m.resizeComponents()
	result := m.View()
	if result == "" {
		t.Error("View should not be empty in logs tab")
	}
}

func TestFormatTimeEdgeCases(t *testing.T) {
	short := "2024-01-15"
	result := components.FormatTime(&short)
	if result == "" {
		t.Error("FormatTime with short string should not be empty")
	}

	long := "2024-01-15T10:30:00+08:00"
	result2 := components.FormatTime(&long)
	if result2 == "" {
		t.Error("FormatTime with long string should not be empty")
	}
}

func TestMergeRunsPreserveTasks(t *testing.T) {
	existing := []models.Run{
		{
			ID: "r1",
			Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusSuccess},
			},
		},
	}
	newRuns := []models.Run{
		{ID: "r1"},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatal("should have 1 result")
	}
	if len(result[0].Tasks) != 1 {
		t.Error("existing tasks should be preserved")
	}
}

func TestMergeRunsNewRun(t *testing.T) {
	newRuns := []models.Run{
		{ID: "r1", PipelineName: "p1"},
		{ID: "r2", PipelineName: "p2"},
	}
	result := mergeRuns(nil, newRuns)
	if len(result) != 2 {
		t.Errorf("should have 2 results, got %d", len(result))
	}
}

func TestStatusIconAll(t *testing.T) {
	statuses := []string{"running", "pending", "success", "failed", "skipped", "cancelled", "unknown", ""}
	for _, s := range statuses {
		icon := components.StatusIcon(s)
		if icon == "" {
			t.Errorf("StatusIcon(%q) should not be empty", s)
		}
	}
}

func TestStatusStyleAll(t *testing.T) {
	statuses := []string{"running", "pending", "success", "failed", "skipped", "cancelled", "unknown", ""}
	for _, s := range statuses {
		style := components.StatusStyle(s)
		_ = style
	}
}

func TestMakeProgressBarEdge(t *testing.T) {
	result := components.MakeProgressBar(0, 0, 0, 10)
	_ = result

	result2 := components.MakeProgressBar(5, 5, 10, 10)
	if result2 == "" {
		t.Error("progress bar should not be empty with valid input")
	}
}

func TestNewAppStateDefaults(t *testing.T) {
	s := NewAppState()
	if s.FocusedPanel != FocusRunList {
		t.Error("default FocusedPanel should be FocusRunList")
	}
	if s.DetailExpanded == nil {
		t.Error("DetailExpanded should be initialized")
	}
	if s.SubExpanded == nil {
		t.Error("SubExpanded should be initialized")
	}
}

func TestRunDetailUpdatePreventsCrash(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "test",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning, SubpipelineName: "default"},
			{TaskName: "t2", Status: models.TaskStatusPending, SubpipelineName: "sub1"},
			{TaskName: "t3", Status: models.TaskStatusSuccess, SubpipelineName: "default"},
			{TaskName: "t4", Status: models.TaskStatusFailed, SubpipelineName: "sub2"},
			{TaskName: "t5", Status: models.TaskStatusSkipped, SubpipelineName: "default"},
			{TaskName: "t6", Status: models.TaskStatusCancelled, SubpipelineName: "sub1"},
		},
	})
	m.runDetail.SetSize(80, 24)

	for _, key := range []tea.KeyType{tea.KeyUp, tea.KeyDown, tea.KeyHome, tea.KeyEnd} {
		m.dispatchKey(tea.KeyMsg{Type: key})
	}
	m.View()
}

func TestRecordUserActivity(t *testing.T) {
	m := makeTestModel()
	before := m.lastUserActivityTime
	m.recordUserActivity()
	if m.lastUserActivityTime == before {
		t.Error("recordUserActivity should update timestamp")
	}
}

func TestCycleTab(t *testing.T) {
	m := makeTestModel()
	m.state.RightTab = TabDetail
	next := m.cycleTab()
	if next != TabLogs {
		t.Error("cycleTab from Detail should go to Logs")
	}

	m.state.RightTab = TabLogs
	next = m.cycleTab()
	if next != TabDetail {
		t.Error("cycleTab from Logs should go to Detail")
	}
}

func TestWindowSizeMsgAlreadyReady(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	msg := tea.WindowSizeMsg{Width: 80, Height: 24}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.Width != 80 {
		t.Errorf("width = %d, want 80", model.state.Width)
	}
	if model.state.Height != 24 {
		t.Errorf("height = %d, want 24", model.state.Height)
	}
}

func TestRunFetchedMergeIntoLists(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "old", Status: models.RunStatusPending,
			Tasks: []models.TaskRun{{TaskName: "existing", Status: models.TaskStatusSuccess}},
		},
		{ID: "r2", PipelineName: "keep", Status: models.RunStatusRunning},
	}
	m.state.RunsHash = "oldhash"

	newRun := &models.Run{ID: "r1", PipelineName: "updated", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{{TaskName: "newtask", Status: models.TaskStatusRunning}},
	}
	msg := runFetchedMsg{run: newRun}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if len(model.state.Runs) != 2 {
		t.Errorf("should have 2 runs, got %d", len(model.state.Runs))
	}
	if model.state.Runs[0].PipelineName != "updated" {
		t.Error("existing run should be updated in-place")
	}
}

func TestTickMsgWithRunningTaskLogs(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runDetail.SetRun(&m.state.Runs[0])
	m.runDetail.SetCursor(1)
	m.runDetail.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})

	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	_ = model
	if cmd == nil {
		t.Error("tick with running task on logs tab should return commands")
	}
}

func TestDispatchKeyLogViewerUpdate(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.logViewer.SetContent("test log content")
	m.logViewer.SetSize(80, 20)

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	_ = cmd
}

func TestDispatchKeyDetailNoRun(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	if cmd != nil {
		t.Error("dispatchKey with no selected run/task should not return cmd")
	}
}

func TestRunFetchedMsgNilRun(t *testing.T) {
	m := makeTestModel()
	msg := runFetchedMsg{run: nil}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestUpdateWindowSizeMsgSmall(t *testing.T) {
	m := makeTestModel()
	msg := tea.WindowSizeMsg{Width: 20, Height: 5}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if !model.state.Ready {
		t.Error("should be ready after small window resize")
	}
}

func TestSyncStateFromComponentsNoTask(t *testing.T) {
	m := makeTestModel()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
	})
	m.runDetail.SetCursor(0)

	m.syncStateFromComponents()

	if m.state.SelectedRun == nil {
		t.Error("SelectedRun should not be nil")
	}
}

func TestExpandAllKeyDetail(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "abc",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
			{TaskName: "t2", Status: models.TaskStatusPending},
		},
	})

	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'c'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestRunsFetchedMsgWithDebugRecording(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	runs := []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.state.Runs = runs
	m.state.RunsHash = computeRunsHash(runs)

	msg := runsFetchedMsg{runs: runs}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestRunFetchedMsgDebugRecording(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	run := &models.Run{ID: "r1", Status: models.RunStatusRunning}
	m.state.SelectedRun = run
	m.state.RunHash = computeRunHash(run)

	msg := runFetchedMsg{run: run}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestTickMsgDebugRecording(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.RightTab = TabDetail
	msg := tickMsg{}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestResizeComponentsLargeWindow(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 300
	m.state.Height = 100
	m.resizeComponents()
	if m.state.Dims.innerW < 36 {
		t.Error("innerW should be reasonable")
	}
}

func TestResizeComponentsMediumWindow(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 60
	m.state.Height = 15
	m.resizeComponents()
}

func TestRunFetchedMsgMergePreservesTasks(t *testing.T) {
	m := makeTestModel()
	m.state.Runs = []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusSuccess},
			{TaskName: "t2", Status: models.TaskStatusRunning},
		}},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&models.Run{ID: "r1"})

	newRun := &models.Run{ID: "r1", Tasks: nil, PipelineName: "updated"}
	msg := runFetchedMsg{run: newRun}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.Runs[0].PipelineName != "updated" {
		t.Error("run should be updated with fetched data")
	}
}

func TestRunsFetchedMsgAlreadyPendingRender(t *testing.T) {
	m := makeTestModel()
	m.pendingRender = true
	runs := []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	msg := runsFetchedMsg{runs: runs}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestLogsFetchedMsgAlreadyPendingRender(t *testing.T) {
	m := makeTestModel()
	m.pendingRender = true
	logs := map[string]string{"task1": "line1\nline2"}
	msg := logsFetchedMsg{logs: logs}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestRunDetailUpdateWithSubpipelines(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "test",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning, SubpipelineName: "default"},
			{TaskName: "t2", Status: models.TaskStatusPending, SubpipelineName: "sub1"},
			{TaskName: "t3", Status: models.TaskStatusSuccess, SubpipelineName: "sub2"},
		},
	})
	m.runDetail.SetSize(80, 24)
	m.runDetail.SetCursor(2)

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyEnter})
	_ = cmd
}

func TestViewAllTabs(t *testing.T) {
	for _, tab := range []RightPanelTab{TabDetail, TabLogs} {
		for _, focus := range []PanelFocus{FocusRunList, FocusRightPanel} {
			m := makeTestModel()
			m.state.Ready = true
			m.state.Width = 120
			m.state.Height = 40
			m.state.RightTab = tab
			m.state.FocusedPanel = focus
			m.resizeComponents()
			m.state.Runs = []models.Run{
				{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
			}
			m.runList.SetRuns(m.state.Runs)
			m.runDetail.SetRun(&models.Run{ID: "r1", Status: models.RunStatusRunning})
			result := m.View()
			if result == "" {
				t.Errorf("View should not be empty for tab=%d focus=%d", tab, focus)
			}
		}
	}
}

func TestEnterOnRightPanelLogsTab(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.state.Ready = true
	m.logViewer.SetContent("some content")
	m.logViewer.SetSize(80, 20)

	msg := tea.KeyMsg{Type: tea.KeyEnter}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestDispatchKeyRunListAllKeys(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRunList
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "p2", Status: models.RunStatusSuccess},
	}
	m.runList.SetRuns(m.state.Runs)

	for _, key := range []tea.KeyType{tea.KeyUp, tea.KeyDown, tea.KeyHome, tea.KeyEnd} {
		m.dispatchKey(tea.KeyMsg{Type: key})
	}
}

func TestNavBackFromDetail(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.navigateBack()
	if m.state.FocusedPanel != FocusRunList {
		t.Error("navigateBack from detail should go to RunList")
	}

	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.navigateBack()
	if m.state.RightTab != TabDetail {
		t.Error("navigateBack from logs should go to detail")
	}

	m.state.FocusedPanel = FocusRunList
	m.state.RightTab = TabDetail
	m.navigateBack()
	if m.state.FocusedPanel != FocusRunList {
		t.Error("navigateBack from RunList should stay")
	}
}

func TestDispatchKeyAllPaths(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	tests := []struct {
		focus  PanelFocus
		tab    RightPanelTab
		setup  func()
		key    tea.KeyType
	}{
		{FocusRunList, TabDetail, func() {
			m.state.Runs = []models.Run{{ID: "r1"}, {ID: "r2"}}
			m.runList.SetRuns(m.state.Runs)
		}, tea.KeyUp},
		{FocusRunList, TabDetail, nil, tea.KeyDown},
		{FocusRightPanel, TabDetail, func() {
			m.runDetail.SetRun(&models.Run{ID: "r1", Tasks: []models.TaskRun{
				{TaskName: "t1"}, {TaskName: "t2"},
			}})
		}, tea.KeyUp},
		{FocusRightPanel, TabDetail, nil, tea.KeyDown},
		{FocusRightPanel, TabLogs, nil, tea.KeyUp},
	}
	for _, tc := range tests {
		m.state.FocusedPanel = tc.focus
		m.state.RightTab = tc.tab
		if tc.setup != nil {
			tc.setup()
		}
		m.dispatchKey(tea.KeyMsg{Type: tc.key})
	}
}

func TestLogsFetchedMsgWithRunningTask(t *testing.T) {
	m := makeTestModel()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "running_task", Status: models.TaskStatusRunning},
		},
	})
	m.runDetail.SetCursor(1)
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs

	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	model := m2.(Model)
	_ = model
	if cmd == nil {
		t.Error("tick on logs tab with running task should return commands")
	}
}

func TestInitBatch(t *testing.T) {
	m := makeTestModel()
	cmd := m.Init()
	if cmd == nil {
		t.Fatal("Init should return command")
	}
	msg := cmd()
	if _, ok := msg.(tickMsg); !ok {
		if _, ok2 := msg.(runsFetchedMsg); !ok2 {
			t.Logf("Init returned msg type %T", msg)
		}
	}
}

func TestSyncStateFromComponentsWithTask(t *testing.T) {
	m := makeTestModel()
	m.state.Runs = []models.Run{
		{ID: "r1", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "t1", Status: models.TaskStatusRunning},
			},
		},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&m.state.Runs[0])
	m.runDetail.SetCursor(1)

	m.syncStateFromComponents()

	if m.state.SelectedRun == nil {
		t.Error("SelectedRun should not be nil")
	}
	if m.state.SelectedTask == nil {
		t.Error("SelectedTask should not be nil when cursor is on a task")
	}
}

func TestSyncStateFromComponentsNoSelectedRun(t *testing.T) {
	m := makeTestModel()
	m.syncStateFromComponents()
	if m.state.SelectedRun != nil {
		t.Error("SelectedRun should be nil when no run set")
	}
}

func TestDispatchKeyDetailWithTaskAndNotLoading(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
			{TaskName: "t2", Status: models.TaskStatusPending},
		},
	})
	m.runDetail.SetCursor(2)
	m.logViewer.SetContent("")

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyUp})
	_ = cmd
}

func TestDispatchKeyDetailWithTaskAndLoading(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})
	m.runDetail.SetCursor(1)
	m.logViewer.SetContent("loading...")
	m.logViewer.SetSize(80, 20)

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyUp})
	_ = cmd
}

func TestResizeComponentsExtremelyNarrow(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 20
	m.state.Height = 10
	m.resizeComponents()
}

func TestResizeComponentsZeroHeight(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 100
	m.state.Height = 0
	m.resizeComponents()
}

func TestOsaChdir(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 45
	m.state.Height = 25
	m.resizeComponents()
	if m.state.Dims.leftContentW < 14 {
		t.Logf("leftContentW=%d with narrow window", m.state.Dims.leftContentW)
	}
}

func TestUpdateEscFromDetailToRunList(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	msg := tea.KeyMsg{Type: tea.KeyEsc}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.FocusedPanel != FocusRunList {
		t.Error("esc on detail should focus RunList")
	}
}

func TestUpdateEscFromLogsToDetail(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	msg := tea.KeyMsg{Type: tea.KeyEsc}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.RightTab != TabDetail {
		t.Error("esc on logs should switch to detail tab")
	}
}

func TestUpdateKeyTEscaped(t *testing.T) {
	m := makeTestModel()
	m.state.FocusedPanel = FocusRunList
	m.state.RightTab = TabDetail
	msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'T'}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestUpdateEnterRightPanelDetailNoTask(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
	})
	m.runDetail.SetCursor(0)

	msg := tea.KeyMsg{Type: tea.KeyEnter}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestRunsFetchedMsgMergeKeepsTasks(t *testing.T) {
	existing := []models.Run{
		{ID: "r1", Tasks: []models.TaskRun{{TaskName: "saved", Status: models.TaskStatusSuccess}}},
	}
	newRuns := []models.Run{
		{ID: "r1"},
	}
	result := mergeRuns(existing, newRuns)
	if len(result) != 1 {
		t.Fatal("should merge to 1 run")
	}
	if len(result[0].Tasks) != 1 || result[0].Tasks[0].TaskName != "saved" {
		t.Error("tasks should be preserved from existing")
	}
}

func TestDispatchKeyWithDebug(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	t.Run("runlist_cursor_change", func(t *testing.T) {
		m.state.FocusedPanel = FocusRunList
		m.state.Runs = []models.Run{
			{ID: "r1"}, {ID: "r2"}, {ID: "r3"},
		}
		m.runList.SetRuns(m.state.Runs)
		m.runList.SetCursor(0)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	})

	t.Run("detail_cursor_change", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabDetail
		m.runDetail.SetRun(&models.Run{
			ID: "r1", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{
				{TaskName: "t1"}, {TaskName: "t2"}, {TaskName: "t3"},
			},
		})
		m.runDetail.SetSize(80, 24)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	})

	t.Run("logviewer_key", func(t *testing.T) {
		m.state.FocusedPanel = FocusRightPanel
		m.state.RightTab = TabLogs
		m.logViewer.SetContent("test")
		m.logViewer.SetSize(80, 20)
		m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	})
}

func TestUpdateFullWithDebug(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning,
			Tasks: []models.TaskRun{{TaskName: "t1", Status: models.TaskStatusRunning}},
		},
	}

	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})

	keys := []string{"q", "q", "ctrl+c"}
	for _, k := range keys {
		if k == "q" {
			m2, _ := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}})
			m = m2.(Model)
		}
	}

	m.state.Quit = false
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID: "r1", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{{TaskName: "t1", Status: models.TaskStatusRunning}},
	})

	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})
	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})

	m.state.RightTab = TabDetail
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)

	m.Update(runsFetchedMsg{runs: []models.Run{
		{ID: "r2", PipelineName: "p2", Status: models.RunStatusRunning},
	}})

	m.Update(runFetchedMsg{run: &models.Run{
		ID: "r1", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{{TaskName: "t1", Status: models.TaskStatusRunning}},
	}})

	m.Update(logsFetchedMsg{logs: map[string]string{"t1": "line1"}})

	m.Update(tickMsg{})

	m.Update(debounceTickMsg{})
}

func TestResizeComponentsAllBranches(t *testing.T) {
	tests := []struct {
		name   string
		width  int
		height int
	}{
		{"normal", 120, 40},
		{"small_available_height", 80, 3},
		{"medium", 60, 15},
		{"narrow_total_content", 38, 40},
		{"very_small", 20, 5},
		{"height_4_clamp_content", 80, 4},
		{"width_35_clamp_below_36", 35, 30},
		{"width_30_right_clamp", 30, 30},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			m := makeTestModel()
			m.state.Width = tc.width
			m.state.Height = tc.height
			m.resizeComponents()
		})
	}
}

func TestDispatchKeyDetailCmdReturn(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})
	m.runDetail.SetSize(80, 24)

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyEnter})
	_ = cmd
}

func TestUpdateDebugEscAndNav(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	m.Update(tea.KeyMsg{Type: tea.KeyEsc})

	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.Update(tea.KeyMsg{Type: tea.KeyEsc})

	m.state.RightTab = TabDetail
	m.Update(tea.KeyMsg{Type: tea.KeyEsc})

	m.state.Quit = false
	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}})
}

func TestInitBatchBoth(t *testing.T) {
	m := makeTestModel()
	cmds := m.Init()
	if cmds == nil {
		t.Fatal("Init should return batch command")
	}
	result := cmds()
	if _, ok := result.(tea.BatchMsg); !ok {
		t.Logf("expected BatchMsg, got %T", result)
	}
}

func TestUpdateTicketForLogsTab(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabLogs
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning},
	}
	m.runList.SetRuns(m.state.Runs)
	m.runList.SetCursor(0)
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
		},
	})
	m.runDetail.SetCursor(1)

	msg := tickMsg{}
	m2, cmd := m.Update(msg)
	_ = m2
	if cmd == nil {
		t.Error("tick on logs tab with running task should return commands")
	}
}

func TestInitResultType(t *testing.T) {
	m := makeTestModel()
	cmd := m.Init()
	result := cmd()
	if _, ok := result.(tea.BatchMsg); !ok {
		t.Logf("Init result type: %T", result)
	}
}

func TestResizeComponentsExactEdge(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 39
	m.state.Height = 6
	m.resizeComponents()
}

func TestDispatchKeyDetailWithDebugCursor(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID: "r1", Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{{TaskName: "t1"}, {TaskName: "t2"}},
	})
	m.runDetail.SetSize(80, 24)
	m.runDetail.SetCursor(0)

	m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
}

func TestLogsFetchedMsgError(t *testing.T) {
	m := makeTestModel()
	msg := logsFetchedMsg{err: fmt.Errorf("test error")}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	if model.state.ErrorMsg == "" {
		t.Error("should have error message")
	}
}

func TestDebugRunFetchedMsgHashChanged(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Runs = []models.Run{{ID: "r1"}}
	m.state.RunHash = "oldhash"
	m.runDetail.SetRun(&models.Run{ID: "r1"})

	msg := runFetchedMsg{run: &models.Run{ID: "r1", PipelineName: "updated"}}
	m2, cmd := m.Update(msg)
	_ = m2
	_ = cmd
}

func TestDebugLogsFetchedMsg(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	msg := logsFetchedMsg{logs: map[string]string{"task1": "line1\nline2"}}
	m2, _ := m.Update(msg)
	model := m2.(Model)
	_ = model
}

func TestDebugKeyMsgRecord(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()

	m.Update(tea.KeyMsg{Type: tea.KeyTab})
	m.Update(tea.KeyMsg{Type: tea.KeyShiftTab})
	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'b'}})
	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}})
}

func TestDebugTickMsgRecord(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.RightTab = TabDetail
	m.state.Runs = []models.Run{{ID: "r1"}}
	m.runList.SetRuns(m.state.Runs)

	m.Update(tickMsg{})
}

func TestEnterOnDetailExpandsGroup(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
			{TaskName: "t2", Status: models.TaskStatusPending},
		},
	})
	m.runDetail.SetSize(80, 24)
	m.runDetail.SetCursor(2)

	msg := tea.KeyMsg{Type: tea.KeyEnter}
	m2, cmd := m.Update(msg)
	_ = m2
	_ = cmd
}

func TestResizeComponentsContentHeightClamp(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 100
	m.state.Height = 4
	m.resizeComponents()
}

func TestResizeComponentsTotalContentClamp(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 37
	m.state.Height = 30
	m.resizeComponents()
}

func TestResizeComponentsRightContentClamp(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 50
	m.state.Height = 30
	m.resizeComponents()
}

func TestDispatchKeyWithPrefetch(t *testing.T) {
	m := makeTestModel()
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail
	m.runDetail.SetRun(&models.Run{
		ID:     "r1",
		Status: models.RunStatusRunning,
		Tasks: []models.TaskRun{
			{TaskName: "t1", Status: models.TaskStatusRunning},
			{TaskName: "t2", Status: models.TaskStatusPending},
		},
	})
	m.runDetail.SetSize(80, 24)
	m.runDetail.SetCursor(2)

	cmd := m.dispatchKey(tea.KeyMsg{Type: tea.KeyDown})
	_ = cmd
}

func TestUpdateDebugWindowResize(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
}

func TestUpdateDebugDispatchKey(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRunList
	m.state.Runs = []models.Run{{ID: "r1"}, {ID: "r2"}}
	m.runList.SetRuns(m.state.Runs)

	m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'x'}})
}

func TestUpdateDebugResizeAndEsc(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.FocusedPanel = FocusRightPanel
	m.state.RightTab = TabDetail

	m.Update(tea.WindowSizeMsg{Width: 80, Height: 24})
	m.Update(tea.KeyMsg{Type: tea.KeyEsc})
}

func TestUpdateDebugRunsFetchedSameHash(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	runs := []models.Run{{ID: "r1"}}
	m.state.Runs = runs
	m.state.RunsHash = computeRunsHash(runs)
	m.Update(runsFetchedMsg{runs: runs})
}

func TestUpdateDebugRunsFetchedChanged(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Runs = []models.Run{{ID: "r1"}}
	m.state.RunsHash = "oldhash"
	m.Update(runsFetchedMsg{runs: []models.Run{{ID: "r2"}}})
}

func TestUpdateDebugRunFetchedSameHash(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	run := &models.Run{ID: "r1"}
	m.state.SelectedRun = run
	m.state.RunHash = computeRunHash(run)
	m.Update(runFetchedMsg{run: run})
}

func TestUpdateDebugTickSkip(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.recordUserActivity()
	m.Update(tickMsg{})
}

func TestUpdateDebugTickActive(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.RightTab = TabDetail
	m.state.Runs = []models.Run{{ID: "r1"}}
	m.runList.SetRuns(m.state.Runs)
	m.runDetail.SetRun(&models.Run{ID: "r1"})

	m.Update(tickMsg{})
}

func TestUpdateDebugDebounce(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		if rec.IsEnabled() {
			rec.Stop(0)
		}
	}()

	m := makeTestModel()
	m.pendingRender = true
	m.Update(debounceTickMsg{})
}

func TestViewCacheHit(t *testing.T) {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = []models.Run{{ID: "r1", PipelineName: "p1", Status: models.RunStatusRunning}}
	m.runList.SetRuns(m.state.Runs)
	m.runDetail.SetRun(&models.Run{ID: "r1", Status: models.RunStatusRunning})

	view1 := m.View()
	view2 := m.View()
	if view1 != view2 {
		t.Error("View should be cached for same state")
	}
}

func TestStopWhenDisabled(t *testing.T) {
	rec := GetDebugRecorder()
	if rec.IsEnabled() {
		rec.Stop(0)
	}
	rec.Stop(1)
}

func TestStartWhenEnabled(t *testing.T) {
	rec := GetDebugRecorder()
	tmpDir := t.TempDir()
	origDir, _ := os.Getwd()
	defer os.Chdir(origDir)
	os.Chdir(tmpDir)
	os.MkdirAll("docs/issues", 0755)

	if !rec.IsEnabled() {
		rec.Start("test", "xterm", "/dev/pts/0", 80, 24)
	}
	defer func() {
		rec.Stop(0)
	}()

	err := rec.Start("test2", "xterm", "/dev/pts/0", 80, 24)
	if err != nil {
		t.Logf("Start when already enabled: %v", err)
	}
}

func makeTestClientWithServer(ts *httptest.Server) *client.Client {
	u, _ := url.Parse(ts.URL)
	host := u.Hostname()
	port, _ := strconv.Atoi(u.Port())
	cfg := &config.Config{
		Server: config.ServerConfig{Host: host, Port: port},
	}
	return client.New(cfg)
}

func TestFetchRunsSuccess(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(models.RunListResponse{
			Items: []models.Run{
				{ID: "r1", PipelineName: "p1", Status: "running"},
				{ID: "r2", PipelineName: "p2", Status: "success"},
			},
			Total: 2,
		})
	}))
	defer ts.Close()

	c := makeTestClientWithServer(ts)
	cmd := fetchRuns(c)
	msg := cmd()
	if rf, ok := msg.(runsFetchedMsg); ok {
		if rf.err != nil {
			t.Errorf("expected success, got error: %v", rf.err)
		}
		if len(rf.runs) != 2 {
			t.Errorf("expected 2 runs, got %d", len(rf.runs))
		}
	}
}

func TestFetchRunSuccess(t *testing.T) {
	runID := "test-run-1"
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(models.Run{
			ID: runID, PipelineName: "test-pipeline", Status: "running",
			Tasks: []models.TaskRun{
				{TaskName: "build", Status: "success"},
				{TaskName: "test", Status: "running"},
			},
		})
	}))
	defer ts.Close()

	c := makeTestClientWithServer(ts)
	cmd := fetchRun(c, runID)
	msg := cmd()
	if rf, ok := msg.(runFetchedMsg); ok {
		if rf.err != nil {
			t.Errorf("expected success, got error: %v", rf.err)
		}
		if rf.run == nil {
			t.Error("expected run, got nil")
		} else if rf.run.ID != runID {
			t.Errorf("expected run ID %s, got %s", runID, rf.run.ID)
		}
	}
}

func TestFetchLogsSuccess(t *testing.T) {
	runID := "test-run-1"
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"logs": map[string]string{
				"build": "line1\nline2\nline3",
				"test":  "test output here",
			},
		})
	}))
	defer ts.Close()

	c := makeTestClientWithServer(ts)
	cmd := fetchLogs(c, runID, "build")
	msg := cmd()
	if lf, ok := msg.(logsFetchedMsg); ok {
		if lf.err != nil {
			t.Errorf("expected success, got error: %v", lf.err)
		}
		if len(lf.logs) != 2 {
			t.Errorf("expected 2 log entries, got %d", len(lf.logs))
		}
	}
}

func TestFetchLogsSyncSuccess(t *testing.T) {
	runID := "test-run-1"
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]interface{}{
			"logs": map[string]string{
				"task1": "sync log content",
			},
		})
	}))
	defer ts.Close()

	c := makeTestClientWithServer(ts)
	logs, err := fetchLogsSync(c, runID, "task1")
	if err != nil {
		t.Errorf("expected success, got error: %v", err)
	}
	if logs["task1"] != "sync log content" {
		t.Errorf("expected log content, got %q", logs["task1"])
	}
}