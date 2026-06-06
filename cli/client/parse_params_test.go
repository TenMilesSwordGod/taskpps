package client

import (
	"testing"
)

func TestParseParams_Empty(t *testing.T) {
	result := ParseParams([]string{})
	if len(result) != 0 {
		t.Errorf("expected empty map, got %d items", len(result))
	}
}

func TestParseParams_Single(t *testing.T) {
	result := ParseParams([]string{"key=value"})
	if result["key"] != "value" {
		t.Errorf("expected value, got %v", result["key"])
	}
}

func TestParseParams_Multiple(t *testing.T) {
	result := ParseParams([]string{"key1=value1", "key2=value2"})
	if result["key1"] != "value1" {
		t.Errorf("expected value1, got %v", result["key1"])
	}
	if result["key2"] != "value2" {
		t.Errorf("expected value2, got %v", result["key2"])
	}
}

func TestParseParams_InvalidFormat(t *testing.T) {
	result := ParseParams([]string{"noequalsign"})
	if len(result) != 0 {
		t.Errorf("expected skip invalid format, got %d items", len(result))
	}
}

func TestParseParams_TrimWhitespace(t *testing.T) {
	result := ParseParams([]string{"  key  =  value  "})
	if result["key"] != "value" {
		t.Errorf("expected value, got %v", result["key"])
	}
}

func TestParseParams_Nested(t *testing.T) {
	result := ParseParams([]string{"a.b.c=123"})
	first, ok := result["a"].(map[string]interface{})
	if !ok {
		t.Fatal("expected nested map")
	}
	second, ok := first["b"].(map[string]interface{})
	if !ok {
		t.Fatal("expected nested map at b")
	}
	if second["c"] != "123" {
		t.Errorf("expected 123, got %v", second["c"])
	}
}

func TestParseParams_MultipleNested(t *testing.T) {
	result := ParseParams([]string{"a.b=1", "a.c=2"})
	a, ok := result["a"].(map[string]interface{})
	if !ok {
		t.Fatal("expected nested map")
	}
	if a["b"] != "1" {
		t.Errorf("expected 1, got %v", a["b"])
	}
	if a["c"] != "2" {
		t.Errorf("expected 2, got %v", a["c"])
	}
}

func TestParseParams_QuotedKey(t *testing.T) {
	// ParseParams does not strip quotes from keys
	result := ParseParams([]string{`"key.with.dots"=value`})
	t.Logf("result: %v", result)
}

func TestBuildNestedMap_Empty(t *testing.T) {
	result := make(map[string]interface{})
	keys := []string{"key"}
	buildNestedMap(result, keys, "value")
	if result["key"] != "value" {
		t.Errorf("expected value, got %v", result["key"])
	}
}

func TestBuildNestedMap_OverwriteNonMap(t *testing.T) {
	result := map[string]interface{}{"a": "not a map"}
	keys := []string{"a", "b"}
	buildNestedMap(result, keys, "value")
	a, ok := result["a"].(map[string]interface{})
	if !ok {
		t.Fatal("expected a to be a map after overwrite")
	}
	if a["b"] != "value" {
		t.Errorf("expected value, got %v", a["b"])
	}
}