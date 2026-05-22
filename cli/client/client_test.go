package client

import (
	"testing"

	"github.com/taskpps/ppsctl/config"
)

func TestParseParams(t *testing.T) {
	testCases := []struct {
		name     string
		input    []string
		expected map[string]interface{}
	}{
		{
			name:  "empty input",
			input: []string{},
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
			name:  "invalid format (no equals)",
			input: []string{"invalid"},
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
