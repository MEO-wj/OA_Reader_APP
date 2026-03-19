package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestMe_RemovesLegacyUserIDField(t *testing.T) {
	gin.SetMode(gin.TestMode)

	h := &AuthHandler{}
	r := gin.New()
	r.GET("/api/auth/me", func(c *gin.Context) {
		c.Set("user_id", "u-1")
		c.Set("username", "alice")
		c.Set("user_name", "Alice")
		c.Set("user_roles", []string{"admin"})
		h.Me(c)
	})

	req := httptest.NewRequest(http.MethodGet, "/api/auth/me", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if _, ok := body["user_id"]; ok {
		t.Fatalf("expected legacy field user_id to be removed")
	}
	if body["id"] != "u-1" {
		t.Fatalf("expected id=u-1, got %v", body["id"])
	}
}
