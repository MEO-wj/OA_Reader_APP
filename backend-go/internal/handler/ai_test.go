package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestClearMemory_InjectsUserIDIntoForwardedBody(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var got map[string]any
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &got)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/clear_memory", func(c *gin.Context) {
		c.Set("user_id", "user-123")
		h.ClearMemory(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/clear_memory", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if got["user_id"] != "user-123" {
		t.Fatalf("expected injected user_id=user-123, got %v", got["user_id"])
	}
}

func TestClearMemory_RequiresUserIDInContext(t *testing.T) {
	gin.SetMode(gin.TestMode)

	called := false
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		called = true
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/clear_memory", h.ClearMemory)

	req := httptest.NewRequest(http.MethodPost, "/api/ai/clear_memory", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 when user_id is missing, got %d", rec.Code)
	}
	if called {
		t.Fatalf("expected forwarder not to be called when user_id is missing")
	}
}
