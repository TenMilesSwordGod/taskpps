package client

import (
	"bufio"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/imroc/req"
	"github.com/taskpps/ppsctl/config"
	"github.com/taskpps/ppsctl/logger"
	"github.com/taskpps/ppsctl/models"
)

type Client struct {
	baseURL string
	http    *req.Req
}

func New(cfg *config.Config) *Client {
	addr := config.GetServerAddr(cfg)
	logger.Debug("Initializing client with server address: %s", addr)
	os.Setenv("NO_PROXY", "127.0.0.1,localhost")
	return &Client{
		baseURL: fmt.Sprintf("http://%s/api", addr),
		http:    req.New(),
	}
}

func (c *Client) HealthCheck() (*models.HealthResponse, error) {
	url := fmt.Sprintf("http://%s/health", config.GetServerAddr(config.App))
	logger.Debug("Making health check request to %s", url)
	resp, err := c.http.Get(url)
	if err != nil {
		logger.Debug("Health check failed: %v", err)
		return nil, fmt.Errorf("connection failed: %w", err)
	}
	var health models.HealthResponse
	if err := resp.ToJSON(&health); err != nil {
		logger.Debug("Failed to parse health check response: %v", err)
		return nil, err
	}
	logger.Debug("Health check passed, status: %s, version: %s", health.Status, health.Version)
	return &health, nil
}

func (c *Client) CreateRun(pipeline string, params map[string]interface{}) (*models.Run, error) {
	body := models.CreateRunRequest{
		Pipeline: pipeline,
		Params:   params,
	}
	resp, err := c.http.Post(c.baseURL+"/runs/", req.BodyJSON(body))
	if err != nil {
		return nil, fmt.Errorf("failed to create run: %w", err)
	}
	if resp.Response().StatusCode != 201 {
		return nil, fmt.Errorf("unexpected status: %s", resp.String())
	}
	var run models.Run
	if err := resp.ToJSON(&run); err != nil {
		return nil, err
	}
	return &run, nil
}

func (c *Client) ListRuns(pipeline, status string, limit int) (*models.RunListResponse, error) {
	params := req.QueryParam{}
	if pipeline != "" {
		params["pipeline"] = pipeline
	}
	if status != "" {
		params["status"] = status
	}
	if limit > 0 {
		params["limit"] = limit
	}
	resp, err := c.http.Get(c.baseURL+"/runs/", params)
	if err != nil {
		return nil, fmt.Errorf("failed to list runs: %w", err)
	}
	var list models.RunListResponse
	if err := resp.ToJSON(&list); err != nil {
		var runs []models.Run
		if err2 := resp.ToJSON(&runs); err2 != nil {
			return nil, err
		}
		list = models.RunListResponse{
			Items: runs,
			Total: len(runs),
		}
	}
	return &list, nil
}

func (c *Client) GetRun(runID string) (*models.Run, error) {
	resp, err := c.http.Get(c.baseURL + "/runs/" + runID)
	if err != nil {
		return nil, fmt.Errorf("failed to get run: %w", err)
	}
	if resp.Response().StatusCode == 404 {
		return nil, fmt.Errorf("run %s not found", runID)
	}
	var run models.Run
	if err := resp.ToJSON(&run); err != nil {
		return nil, err
	}
	return &run, nil
}

func (c *Client) GetLogs(runID, task string, tail int) (map[string]string, error) {
	params := req.QueryParam{}
	if task != "" {
		params["task"] = task
	}
	if tail > 0 {
		params["tail"] = tail
	}
	resp, err := c.http.Get(c.baseURL+"/runs/"+runID+"/logs", params)
	if err != nil {
		return nil, fmt.Errorf("failed to get logs: %w", err)
	}
	var result struct {
		Logs map[string]string `json:"logs"`
	}
	if err := resp.ToJSON(&result); err != nil {
		return nil, err
	}
	return result.Logs, nil
}

func (c *Client) FollowLogs(runID, task string, handler func(taskName, line string)) error {
	url := fmt.Sprintf("%s/runs/%s/logs?follow=true", c.baseURL, runID)
	if task != "" {
		url += "&task=" + task
	}

	httpReq, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}
	httpResp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("failed to connect to log stream: %w", err)
	}
	defer httpResp.Body.Close()

	if httpResp.StatusCode != 200 {
		body, _ := io.ReadAll(httpResp.Body)
		return fmt.Errorf("unexpected status %d: %s", httpResp.StatusCode, body)
	}

	scanner := bufio.NewScanner(httpResp.Body)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "event: ") {
			eventName := strings.TrimPrefix(line, "event: ")
			if eventName == "done" {
				break
			}
			continue
		}
		if strings.HasPrefix(line, "data: ") {
			data := strings.TrimPrefix(line, "data: ")
			if idx := strings.Index(data, ": "); idx > 0 {
				taskName := data[:idx]
				content := data[idx+2:]
				handler(taskName, content)
			} else {
				handler("", data)
			}
		}
	}
	return scanner.Err()
}

func (c *Client) CancelRun(runID string) error {
	resp, err := c.http.Post(c.baseURL+"/runs/"+runID+"/cancel", nil)
	if err != nil {
		return fmt.Errorf("failed to cancel run: %w", err)
	}
	if resp.Response().StatusCode == 404 {
		return fmt.Errorf("run %s not found", runID)
	}
	return nil
}

func (c *Client) CleanRuns(olderThan, keep int, force bool) (*models.CleanResponse, error) {
	params := req.QueryParam{}
	if olderThan > 0 {
		params["older_than"] = olderThan
	}
	if keep > 0 {
		params["keep"] = keep
	}
	if force {
		params["force"] = true
	}
	resp, err := c.http.Delete(c.baseURL+"/runs/", params)
	if err != nil {
		return nil, fmt.Errorf("failed to clean runs: %w", err)
	}
	var result models.CleanResponse
	if err := resp.ToJSON(&result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) CreateTrigger(reqBody models.CreateTriggerRequest) (*models.Trigger, error) {
	resp, err := c.http.Post(c.baseURL+"/plugins/triggers/", req.BodyJSON(reqBody))
	if err != nil {
		return nil, fmt.Errorf("failed to create trigger: %w", err)
	}
	var trigger models.Trigger
	if err := resp.ToJSON(&trigger); err != nil {
		return nil, err
	}
	return &trigger, nil
}

func (c *Client) ListTriggers() ([]models.Trigger, error) {
	resp, err := c.http.Get(c.baseURL + "/plugins/triggers/")
	if err != nil {
		return nil, fmt.Errorf("failed to list triggers: %w", err)
	}
	var result struct {
		Items []models.Trigger `json:"items"`
	}
	if err := resp.ToJSON(&result); err != nil {
		var triggers []models.Trigger
		if err2 := resp.ToJSON(&triggers); err2 != nil {
			return nil, err
		}
		return triggers, nil
	}
	return result.Items, nil
}

func (c *Client) DeleteTrigger(triggerID string) error {
	resp, err := c.http.Delete(c.baseURL + "/plugins/triggers/" + triggerID)
	if err != nil {
		return fmt.Errorf("failed to delete trigger: %w", err)
	}
	if resp.Response().StatusCode == 404 {
		return fmt.Errorf("trigger %s not found", triggerID)
	}
	return nil
}

func ParseParams(raw []string) map[string]interface{} {
	result := make(map[string]interface{})
	for _, p := range raw {
		parts := strings.SplitN(p, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.TrimSpace(parts[1])

		keys := strings.Split(key, ".")
		buildNestedMap(result, keys, val)
	}
	return result
}

func buildNestedMap(m map[string]interface{}, keys []string, val string) {
	for i := 0; i < len(keys)-1; i++ {
		k := keys[i]
		if strings.HasPrefix(k, `"`) && strings.HasSuffix(k, `"`) {
			k = k[1 : len(k)-1]
		}
		if _, ok := m[k]; !ok {
			m[k] = make(map[string]interface{})
		}
		next, ok := m[k].(map[string]interface{})
		if !ok {
			next = make(map[string]interface{})
			m[k] = next
		}
		m = next
	}
	lastKey := keys[len(keys)-1]
	if strings.HasPrefix(lastKey, `"`) && strings.HasSuffix(lastKey, `"`) {
		lastKey = lastKey[1 : len(lastKey)-1]
	}
	m[lastKey] = val
}

func init() {
	req.Debug = false
}
