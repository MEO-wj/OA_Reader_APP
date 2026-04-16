package handler

import (
	"bytes"
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

func TestAsk_InjectsUserIDIntoForwardedBody(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var (
		gotPath string
		gotBody map[string]any
	)
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		gotPath = path
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/ask", func(c *gin.Context) {
		c.Set("user_id", "user-999")
		h.Ask(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/ask", io.NopCloser(bytes.NewBufferString(`{"question":"hi"}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if gotPath != "/ask" {
		t.Fatalf("expected forwarded path /ask, got %s", gotPath)
	}
	if gotBody["user_id"] != "user-999" {
		t.Fatalf("expected injected user_id=user-999, got %v", gotBody["user_id"])
	}
}

func TestChat_InjectsUserIDIntoForwardedBody(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var (
		gotPath string
		gotBody map[string]any
	)
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		gotPath = path
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/chat", func(c *gin.Context) {
		c.Set("user_id", "user-chat")
		h.Chat(c)
	})

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/ai/chat",
		io.NopCloser(bytes.NewBufferString(`{"message":"hello","top_k":3,"display_name":"Alice","conversation_id":"conv-1"}`)),
	)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if gotPath != "/chat" {
		t.Fatalf("expected forwarded path /chat, got %s", gotPath)
	}
	if gotBody["user_id"] != "user-chat" {
		t.Fatalf("expected injected user_id=user-chat, got %v", gotBody["user_id"])
	}
	if gotBody["message"] != "hello" {
		t.Fatalf("expected message to be preserved, got %v", gotBody["message"])
	}
	if gotBody["conversation_id"] != "conv-1" {
		t.Fatalf("expected conversation_id to be preserved, got %v", gotBody["conversation_id"])
	}
}
