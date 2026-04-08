package alog

import (
	"bytes"
	"log"
	"strings"
	"testing"
)

func TestAuthf_Disabled_NoOutput(t *testing.T) {
	var buf bytes.Buffer
	oldWriter := log.Writer()
	log.SetOutput(&buf)
	defer log.SetOutput(oldWriter)

	SetAuthDebug(false)
	Authf("[AUTH] this should not print")

	if buf.Len() != 0 {
		t.Fatalf("expected no log output when disabled, got %q", buf.String())
	}
}

func TestAuthf_Enabled_HasOutput(t *testing.T) {
	var buf bytes.Buffer
	oldWriter := log.Writer()
	log.SetOutput(&buf)
	defer log.SetOutput(oldWriter)

	SetAuthDebug(true)
	Authf("[AUTH] user=%s", "alice")

	if !strings.Contains(buf.String(), "user=alice") {
		t.Fatalf("expected log output when enabled, got %q", buf.String())
	}
}
