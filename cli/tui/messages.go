package tui

import "github.com/taskpps/ppsctl/models"

type runsFetchedMsg struct {
	runs []models.Run
	err  error
}

type runFetchedMsg struct {
	run *models.Run
	err error
}

type logsFetchedMsg struct {
	logs map[string]string
	err  error
}

type tickMsg struct{}

type debounceTickMsg struct{}