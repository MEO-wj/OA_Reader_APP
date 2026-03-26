package main

import (
	"testing"

	"github.com/oap/backend-go/internal/config"
)

func TestNewCORSConfigAllowsPatchRequests(t *testing.T) {
	cfg := &config.Config{
		CORSAllowOrigins: []string{"http://localhost:8081"},
	}

	corsCfg := newCORSConfig(cfg)

	if !contains(corsCfg.AllowMethods, "PATCH") {
		t.Fatalf("expected PATCH to be allowed, got %#v", corsCfg.AllowMethods)
	}
}

func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
