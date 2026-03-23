package model

import (
	"encoding/json"
	"testing"
)

func TestJSONArray_Scan_ByteSlice(t *testing.T) {
	var arr JSONArray
	data := []byte(`[{"name":"file.pdf","url":"http://example.com/file.pdf"}]`)

	err := arr.Scan(data)
	if err != nil {
		t.Fatalf("Scan failed: %v", err)
	}

	if len(arr) != 1 {
		t.Fatalf("expected 1 element, got %d", len(arr))
	}
	if arr[0]["name"] != "file.pdf" {
		t.Fatalf("expected name 'file.pdf', got '%s'", arr[0]["name"])
	}
}

func TestJSONArray_Scan_String(t *testing.T) {
	var arr JSONArray
	data := `[{"name":"doc.docx","url":"http://example.com/doc.docx"}]`

	err := arr.Scan(data)
	if err != nil {
		t.Fatalf("Scan failed: %v", err)
	}

	if len(arr) != 1 {
		t.Fatalf("expected 1 element, got %d", len(arr))
	}
	if arr[0]["url"] != "http://example.com/doc.docx" {
		t.Fatalf("expected url 'http://example.com/doc.docx', got '%s'", arr[0]["url"])
	}
}

func TestJSONArray_Scan_Nil(t *testing.T) {
	var arr JSONArray
	err := arr.Scan(nil)
	if err != nil {
		t.Fatalf("Scan nil failed: %v", err)
	}
	if arr != nil {
		t.Fatalf("expected nil, got %v", arr)
	}
}

func TestJSONArray_Scan_EmptyString(t *testing.T) {
	var arr JSONArray
	err := arr.Scan("")
	if err != nil {
		t.Fatalf("Scan empty string failed: %v", err)
	}
}

func TestJSONArray_Scan_InvalidJSON(t *testing.T) {
	var arr JSONArray
	err := arr.Scan([]byte(`{invalid json}`))
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}
}

func TestJSONArray_Value(t *testing.T) {
	arr := JSONArray{
		{"name": "a.txt", "url": "http://example.com/a.txt"},
		{"name": "b.txt", "url": "http://example.com/b.txt"},
	}

	val, err := arr.Value()
	if err != nil {
		t.Fatalf("Value failed: %v", err)
	}

	// 验证序列化结果
	var result []map[string]string
	err = json.Unmarshal(val.([]byte), &result)
	if err != nil {
		t.Fatalf("Value result is not valid JSON: %v", err)
	}
	if len(result) != 2 {
		t.Fatalf("expected 2 elements, got %d", len(result))
	}
}

func TestJSONArray_Value_Nil(t *testing.T) {
	var arr JSONArray
	val, err := arr.Value()
	if err != nil {
		t.Fatalf("Value nil failed: %v", err)
	}
	// nil slice 应该返回 "[]"
	if val != "[]" {
		t.Fatalf("expected '[]', got %v", val)
	}
}
