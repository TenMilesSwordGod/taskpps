package client

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/imroc/req"
	"github.com/taskpps/ppsctl/config"
)

func TestParseParams(t *testing.T) {
	testCases := []struct {
		name     string
		input    []string
		expected map[string]interface{}
	}{
		{
			name:     "empty input",
			input:    []string{},
			expected: map[string]interface{}{},
		},
		{
			name:  "single key-value",
			input: []string{"key=value"},
			expected: map[string]interface{}{
				"key": "value",
			},
		},
		{
			name:  "multiple key-values",
			input: []string{"key1=value1", "key2=value2"},
			expected: map[string]interface{}{
				"key1": "value1",
				"key2": "value2",
			},
		},
		{
			name:  "nested keys",
			input: []string{"a.b.c=123"},
			expected: map[string]interface{}{
				"a": map[string]interface{}{
					"b": map[string]interface{}{
						"c": "123",
					},
				},
			},
		},
		{
			name:     "invalid format (no equals)",
			input:    []string{"invalid"},
			expected: map[string]interface{}{},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := ParseParams(tc.input)

			if len(result) != len(tc.expected) {
				t.Errorf("ParseParams() returned %d items, want %d", len(result), len(tc.expected))
			}

			deepCompare(t, result, tc.expected)
		})
	}
}

func TestBuildNestedMap(t *testing.T) {
	testCases := []struct {
		name     string
		keys     []string
		value    string
		prepop   map[string]interface{}
		expected map[string]interface{}
	}{
		{
			name:   "simple key",
			keys:   []string{"key"},
			value:  "value",
			prepop: nil,
			expected: map[string]interface{}{
				"key": "value",
			},
		},
		{
			name:   "nested keys",
			keys:   []string{"a", "b", "c"},
			value:  "123",
			prepop: nil,
			expected: map[string]interface{}{
				"a": map[string]interface{}{
					"b": map[string]interface{}{
						"c": "123",
					},
				},
			},
		},
		{
			name:   "quoted key",
			keys:   []string{`"my.key"`},
			value:  "value",
			prepop: nil,
			expected: map[string]interface{}{
				"my.key": "value",
			},
		},
		{
			name:   "quoted nested key",
			keys:   []string{`"parent.key"`, "child"},
			value:  "test",
			prepop: nil,
			expected: map[string]interface{}{
				"parent.key": map[string]interface{}{
					"child": "test",
				},
			},
		},
		{
			name:   "existing map replaced",
			keys:   []string{"a", "b"},
			value:  "test",
			prepop: map[string]interface{}{"a": "not a map"},
			expected: map[string]interface{}{
				"a": map[string]interface{}{
					"b": "test",
				},
			},
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			var result map[string]interface{}
			if tc.prepop != nil {
				result = tc.prepop
			} else {
				result = make(map[string]interface{})
			}
			buildNestedMap(result, tc.keys, tc.value)

			if len(result) != len(tc.expected) {
				t.Errorf("buildNestedMap() returned %d items, want %d", len(result), len(tc.expected))
			}

			deepCompare(t, result, tc.expected)
		})
	}
}

func deepCompare(t *testing.T, got, want map[string]interface{}) {
	for k, v := range want {
		if got[k] == nil {
			t.Errorf("missing key: %s", k)
			continue
		}

		switch v.(type) {
		case map[string]interface{}:
			gotMap, ok := got[k].(map[string]interface{})
			if !ok {
				t.Errorf("key %s is not a map", k)
				continue
			}
			deepCompare(t, gotMap, v.(map[string]interface{}))
		default:
			if got[k] != v {
				t.Errorf("key %s: got %v, want %v", k, got[k], v)
			}
		}
	}
}

func TestNew(t *testing.T) {
	cfg := &config.Config{
		Server: config.ServerConfig{
			Host: "localhost",
			Port: 8080,
		},
	}
	client := New(cfg)
	if client == nil {
		t.Fatal("New returned nil")
	}
	if client.baseURL != "http://localhost:8080/api" {
		t.Errorf("baseURL = %s, want http://localhost:8080/api", client.baseURL)
	}
}

func TestParseResp_Success(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		w.Write([]byte(`{"status": "ok"}`))
	}))
	defer ts.Close()

	r := req.New()
	resp, err := r.Get(ts.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var result struct {
		Status string `json:"status"`
	}
	if err := parseResp(resp, &result); err != nil {
		t.Fatalf("parseResp returned error: %v", err)
	}
	if result.Status != "ok" {
		t.Errorf("got status %q, want %q", result.Status, "ok")
	}
}

func TestParseResp_NonJSONResponse(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		w.WriteHeader(200)
		w.Write([]byte(`<!DOCTYPE html><html><body>Internal Server Error</body></html>`))
	}))
	defer ts.Close()

	r := req.New()
	resp, err := r.Get(ts.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var result struct{}
	err = parseResp(resp, &result)
	if err == nil {
		t.Fatal("parseResp should return error for non-JSON 200 response")
	}
	if !contains(err.Error(), "failed to parse response") {
		t.Errorf("error should mention parse failure, got: %v", err)
	}
	if !contains(err.Error(), "DOCTYPE") {
		t.Errorf("error should include raw body for debugging, got: %v", err)
	}
}

func TestParseResp_HTTPError(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(502)
		w.Write([]byte(`<html><body><h1>502 Bad Gateway</h1></body></html>`))
	}))
	defer ts.Close()

	r := req.New()
	resp, err := r.Get(ts.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var result struct{}
	err = parseResp(resp, &result)
	if err == nil {
		t.Fatal("parseResp should return error for 502 response")
	}
	if !contains(err.Error(), "unexpected status 502") {
		t.Errorf("error should mention status code, got: %v", err)
	}
	if !contains(err.Error(), "Bad Gateway") {
		t.Errorf("error should include response body, got: %v", err)
	}
}

func TestParseResp_404Error(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(404)
		w.Write([]byte(`{"detail": "Not found"}`))
	}))
	defer ts.Close()

	r := req.New()
	resp, err := r.Get(ts.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var result struct{}
	err = parseResp(resp, &result)
	if err == nil {
		t.Fatal("parseResp should return error for 404 response")
	}
	if !contains(err.Error(), "unexpected status 404") {
		t.Errorf("error should mention status code, got: %v", err)
	}
}

func TestParseResp_500WithHTML(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		w.Write([]byte(`Internal Server Error`))
	}))
	defer ts.Close()

	r := req.New()
	resp, err := r.Get(ts.URL)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var result struct{}
	err = parseResp(resp, &result)
	if err == nil {
		t.Fatal("parseResp should return error for 500 response")
	}
	if !contains(err.Error(), "unexpected status 500") {
		t.Errorf("error should mention status code, got: %v", err)
	}
	if !contains(err.Error(), "Internal Server Error") {
		t.Errorf("error should include response body, got: %v", err)
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsStr(s, substr))
}

func containsStr(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
