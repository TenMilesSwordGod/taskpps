package tui

import (
	"net/http/httptest"
	"net/url"
	"strconv"

	"github.com/taskpps/ppsctl/client"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/models"
)

func makeTestModel() Model {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	c := client.New(cfg)
	return NewModel(c, "")
}

func makeTestModelWithRuns() Model {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	m.state.Runs = []models.Run{
		{ID: "r1", PipelineName: "deploy", Status: models.RunStatusRunning},
		{ID: "r2", PipelineName: "build", Status: models.RunStatusSuccess},
	}
	m.runList.SetRuns(m.state.Runs)
	return m
}

func makeTestClient() *client.Client {
	cfg := &config.Config{
		Server: config.ServerConfig{Host: "localhost", Port: 8080},
	}
	return client.New(cfg)
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

func makeReadyModel() Model {
	m := makeTestModel()
	m.state.Ready = true
	m.state.Width = 120
	m.state.Height = 40
	m.resizeComponents()
	return m
}

func makeReadyModelWithRuns(runs []models.Run) Model {
	m := makeReadyModel()
	m.state.Runs = runs
	m.runList.SetRuns(runs)
	m.runList.SetCursor(0)
	if len(runs) > 0 {
		m.runDetail.SetRun(&runs[0])
	}
	return m
}
