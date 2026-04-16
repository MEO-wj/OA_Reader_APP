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
	if gotPath != "/chat" {
		t.Fatalf("expected /ask to proxy to /chat, got %s", gotPath)
	}
	if gotBody["user_id"] != "user-999" {
		t.Fatalf("expected injected user_id=user-999, got %v", gotBody["user_id"])
	}
	// /ask remaps question → message when proxying to /chat
	if gotBody["message"] != "hi" {
		t.Fatalf("expected message=hi (remapped from question), got %v", gotBody["message"])
	}
	if _, exists := gotBody["question"]; exists {
		t.Fatalf("expected 'question' key to be removed after remapping")
	}
}

func TestAsk_RemovesTopKField(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var gotBody map[string]any
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/ask", func(c *gin.Context) {
		c.Set("user_id", "user-123")
		h.Ask(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/ask",
		io.NopCloser(bytes.NewBufferString(`{"question":"hi","top_k":10}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if _, exists := gotBody["top_k"]; exists {
		t.Fatalf("expected top_k to be removed")
	}
}

func TestChat_ProxiesToChatEndpoint(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var gotPath string
	var gotBody map[string]any
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		gotPath = path
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/chat", func(c *gin.Context) {
		c.Set("user_id", "user-chat-1")
		h.Chat(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/chat",
		io.NopCloser(bytes.NewBufferString(`{"message":"hello","conversation_id":"conv-1"}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if gotPath != "/chat" {
		t.Fatalf("expected forwarded path /chat, got %s", gotPath)
	}
	if gotBody["user_id"] != "user-chat-1" {
		t.Fatalf("expected injected user_id, got %v", gotBody["user_id"])
	}
	if gotBody["message"] != "hello" {
		t.Fatalf("expected message=hello, got %v", gotBody["message"])
	}
}

func TestChat_RequiresUserID(t *testing.T) {
	gin.SetMode(gin.TestMode)

	called := false
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		called = true
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/chat", h.Chat)

	req := httptest.NewRequest(http.MethodPost, "/api/ai/chat",
		io.NopCloser(bytes.NewBufferString(`{"message":"hello"}`)))
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	if called {
		t.Fatalf("forward should not be called when user_id missing")
	}
}

func TestInjectUserProfile_InjectsProfileFields(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var gotBody map[string]any
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/chat", func(c *gin.Context) {
		c.Set("user_id", "user-456")
		profile := map[string]interface{}{
			"display_name": "张三",
			"profile_tags": []interface{}{"计算机", "夜猫子"},
			"bio":          "大三学生",
		}
		c.Set("user_profile", profile)
		h.Chat(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/chat",
		io.NopCloser(bytes.NewBufferString(`{"message":"test"}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if gotBody["display_name"] != "张三" {
		t.Fatalf("expected display_name=张三, got %v", gotBody["display_name"])
	}
	tags, ok := gotBody["profile_tags"].([]interface{})
	if !ok || len(tags) != 2 {
		t.Fatalf("expected 2 profile_tags, got %v", gotBody["profile_tags"])
	}
	if gotBody["bio"] != "大三学生" {
		t.Fatalf("expected bio=大三学生, got %v", gotBody["bio"])
	}
}

func TestInjectUserProfile_HandlesStringSliceTags(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var gotBody map[string]any
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/chat", func(c *gin.Context) {
		c.Set("user_id", "user-789")
		// middleware stores []string (from ProfileService), not []interface{}
		profile := map[string]interface{}{
			"display_name": "李四",
			"profile_tags": []string{"计算机", "夜猫子"},
			"bio":          "大四学生",
		}
		c.Set("user_profile", profile)
		h.Chat(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/chat",
		io.NopCloser(bytes.NewBufferString(`{"message":"test"}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if gotBody["display_name"] != "李四" {
		t.Fatalf("expected display_name=李四, got %v", gotBody["display_name"])
	}
	tags, ok := gotBody["profile_tags"].([]interface{})
	if !ok || len(tags) != 2 {
		t.Fatalf("expected 2 profile_tags as []interface{}, got %v (%T)", gotBody["profile_tags"], gotBody["profile_tags"])
	}
}

func TestInjectUserProfile_SkipsWhenNoProfile(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var gotBody map[string]any
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		body, _ := io.ReadAll(c.Request.Body)
		_ = json.Unmarshal(body, &gotBody)
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/chat", func(c *gin.Context) {
		c.Set("user_id", "user-000")
		// no user_profile in context
		h.Chat(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/chat",
		io.NopCloser(bytes.NewBufferString(`{"message":"test"}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if gotBody["display_name"] != nil {
		t.Fatalf("expected no display_name when no profile, got %v", gotBody["display_name"])
	}
}
