package tui

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"

	"github.com/taskpps/ppsctl/models"
)

type AppState struct {
	Runs     []models.Run
	RunsHash string

	SelectedRun  *models.Run
	RunHash      string
	SelectedTask *models.TaskRun

	FocusedPanel PanelFocus
	RightTab     RightPanelTab

	RunListCursor  int
	DetailExpanded map[int]bool
	SubExpanded    map[string]bool
	DetailCursor   int

	LogContent string
	LogLoading bool

	ErrorMsg string
	Quit     bool

	Width  int
	Height int
	Ready  bool
	Dims   layoutDims

	viewHash string
}

func NewAppState() AppState {
	return AppState{
		FocusedPanel:   FocusRunList,
		DetailExpanded: make(map[int]bool),
		SubExpanded:    make(map[string]bool),
	}
}

func (s AppState) Copy() AppState {
	cp := s
	cp.DetailExpanded = make(map[int]bool, len(s.DetailExpanded))
	for k, v := range s.DetailExpanded {
		cp.DetailExpanded[k] = v
	}
	cp.SubExpanded = make(map[string]bool, len(s.SubExpanded))
	for k, v := range s.SubExpanded {
		cp.SubExpanded[k] = v
	}
	if s.SelectedRun != nil {
		runCopy := *s.SelectedRun
		cp.SelectedRun = &runCopy
	}
	return cp
}

func (s AppState) computeViewHash() string {
	data, _ := json.Marshal(s)
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

func (s AppState) IsViewSameAs(other AppState) bool {
	if s.viewHash == "" {
		return false
	}
	if other.viewHash == "" {
		return false
	}
	return s.viewHash == other.viewHash
}