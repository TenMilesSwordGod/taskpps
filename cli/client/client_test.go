package client

import (
	"testing"
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
		expected map[string]interface{}
	}{
		{
			name:  "simple key",
			keys:  []string{"key"},
			value: "value",
			expected: map[string]interface{}{
				"key": "value",
			},
		},
		{
			name:  "nested keys",
			keys:  []string{"a", "b", "c"},
			value: "123",
			expected: map[string]interface{}{
				"a": map[string]interface{}{
					"b": map[string]interface{}{
						"c": "123",
					},
				},
			},
		},

	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			result := make(map[string]interface{})
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
