package model

import (
	"encoding/json"
	"testing"
)

func TestJSONMap_Value_NilReturnsEmptyObject(t *testing.T) {
	var m JSONMap
	val, err := m.Value()
	if err != nil {
		t.Fatalf("Value failed: %v", err)
	}
	if val != "{}" {
		t.Fatalf("expected {}, got %v", val)
	}
}

func TestJSONMap_Scan_ByteSlice(t *testing.T) {
	var m JSONMap
	if err := m.Scan([]byte(`{"k":"v"}`)); err != nil {
		t.Fatalf("Scan failed: %v", err)
	}
	if m["k"] != "v" {
		t.Fatalf("expected v, got %v", m["k"])
	}

	raw, _ := m.Value()
	var decoded map[string]any
	_ = json.Unmarshal(raw.([]byte), &decoded)
	if decoded["k"] != "v" {
		t.Fatalf("expected v after marshal, got %v", decoded["k"])
	}
}
