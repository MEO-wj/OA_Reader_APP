package model

import (
	"reflect"
	"strings"
	"testing"
)

func TestVectorEmbeddingTagUses1024Dimension(t *testing.T) {
	field, ok := reflect.TypeOf(Vector{}).FieldByName("Embedding")
	if !ok {
		t.Fatal("Embedding field not found")
	}
	tag := field.Tag.Get("gorm")
	if !strings.Contains(tag, "vector(1024)") {
		t.Fatalf("expected vector(1024), got %s", tag)
	}
}
