package model

import (
	"reflect"
	"testing"
)

func TestStringArray_Scan_String(t *testing.T) {
	var arr StringArray

	err := arr.Scan(`{"计算机","AI"}`)
	if err != nil {
		t.Fatalf("Scan failed: %v", err)
	}

	want := StringArray{"计算机", "AI"}
	if !reflect.DeepEqual(arr, want) {
		t.Fatalf("expected %v, got %v", want, arr)
	}
}

func TestStringArray_Scan_ByteSlice(t *testing.T) {
	var arr StringArray

	err := arr.Scan([]byte(`{"a","b"}`))
	if err != nil {
		t.Fatalf("Scan failed: %v", err)
	}

	want := StringArray{"a", "b"}
	if !reflect.DeepEqual(arr, want) {
		t.Fatalf("expected %v, got %v", want, arr)
	}
}

func TestStringArray_Scan_Nil(t *testing.T) {
	var arr StringArray

	err := arr.Scan(nil)
	if err != nil {
		t.Fatalf("Scan nil failed: %v", err)
	}

	if arr != nil {
		t.Fatalf("expected nil, got %v", arr)
	}
}

func TestStringArray_Value_RoundTrip(t *testing.T) {
	original := StringArray{"计算机", "AI"}

	val, err := original.Value()
	if err != nil {
		t.Fatalf("Value failed: %v", err)
	}

	var decoded StringArray
	if err := decoded.Scan(val); err != nil {
		t.Fatalf("round trip scan failed: %v", err)
	}

	if !reflect.DeepEqual(decoded, original) {
		t.Fatalf("expected %v, got %v", original, decoded)
	}
}
