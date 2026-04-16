package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/gin-gonic/gin"
)

type AIHandler struct {
	aiEndURL string
	forward  func(c *gin.Context, path string)
	queue    *AIRequestQueue
}

func NewAIHandler(aiEndURL string, queue *AIRequestQueue) *AIHandler {
	h := &AIHandler{aiEndURL: aiEndURL, queue: queue}
	h.forward = h.defaultForward
	return h
}

func NewAIHandlerWithForward(forward func(c *gin.Context, path string)) *AIHandler {
	return &AIHandler{forward: forward, queue: NewAIRequestQueue(2)}
}

func (h *AIHandler) defaultForward(c *gin.Context, path string) {
	target, _ := url.Parse(h.aiEndURL)
	proxy := httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.URL.Path = path
		},
	}
	proxy.ServeHTTP(c.Writer, c.Request)
}

func (h *AIHandler) proxy(c *gin.Context, path string) {
	h.forward(c, path)
}

// Chat handles /chat requests: inject user_id + profile -> enqueue -> proxy
func (h *AIHandler) Chat(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	injectUserProfile(c)
	h.queuedProxy(c, "/chat")
}

// Ask is the compat endpoint: remap question->message, then proxy to /chat
func (h *AIHandler) Ask(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	remapAskToChat(c)
	injectUserProfile(c)
	h.queuedProxy(c, "/chat")
}

// ClearMemory keeps original logic (low frequency, no queue needed)
func (h *AIHandler) ClearMemory(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	h.proxy(c, "/clear_memory")
}

func (h *AIHandler) Embed(c *gin.Context) {
	h.proxy(c, "/embed")
}

// queuedProxy enqueues the request to control concurrency
func (h *AIHandler) queuedProxy(c *gin.Context, path string) {
	done := h.queue.Enqueue(c.Request.Context(), func(ctx context.Context) {
		h.forward(c, path)
	})
	<-done
}

// injectUserID injects user_id from JWT context into request body
func injectUserID(c *gin.Context) bool {
	userID, ok := c.Get("user_id")
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user_id"})
		return false
	}

	payload := map[string]interface{}{}
	if c.Request.Body != nil {
		body, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request body"})
			return false
		}
		if len(bytes.TrimSpace(body)) > 0 {
			if err := json.Unmarshal(body, &payload); err != nil {
				c.JSON(http.StatusBadRequest, gin.H{"error": "invalid json"})
				return false
			}
		}
	}
	payload["user_id"] = userID
	bodyBytes, _ := json.Marshal(payload)
	c.Request.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	c.Request.ContentLength = int64(len(bodyBytes))
	c.Request.Header.Set("Content-Type", "application/json")
	return true
}

// injectUserProfile reads user profile from context and injects into request body.
// It handles both []string and []interface{} for profile_tags.
func injectUserProfile(c *gin.Context) {
	profile, ok := c.Get("user_profile")
	if !ok {
		return
	}
	profileMap, ok := profile.(map[string]interface{})
	if !ok {
		return
	}

	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		return
	}
	var payload map[string]interface{}
	if len(bytes.TrimSpace(body)) > 0 {
		if err := json.Unmarshal(body, &payload); err != nil {
			return
		}
	} else {
		payload = map[string]interface{}{}
	}

	if dn, ok := profileMap["display_name"].(string); ok && dn != "" {
		payload["display_name"] = dn
	}
	if bio, ok := profileMap["bio"].(string); ok && bio != "" {
		payload["bio"] = bio
	}
	// Handle profile_tags: could be []string (from middleware) or []interface{} (from JSON)
	if tags := extractStringSlice(profileMap["profile_tags"]); len(tags) > 0 {
		payload["profile_tags"] = tags
	}

	bodyBytes, _ := json.Marshal(payload)
	c.Request.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	c.Request.ContentLength = int64(len(bodyBytes))
}

// extractStringSlice converts both []string and []interface{} to []interface{} for JSON serialization.
func extractStringSlice(val interface{}) []interface{} {
	if val == nil {
		return nil
	}
	switch v := val.(type) {
	case []string:
		result := make([]interface{}, len(v))
		for i, s := range v {
			result[i] = s
		}
		return result
	case []interface{}:
		return v
	}
	return nil
}

// remapAskToChat maps old /ask fields to /chat format
func remapAskToChat(c *gin.Context) {
	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		return
	}
	var payload map[string]interface{}
	if len(bytes.TrimSpace(body)) > 0 {
		_ = json.Unmarshal(body, &payload)
	} else {
		payload = map[string]interface{}{}
	}

	if q, ok := payload["question"]; ok {
		payload["message"] = q
		delete(payload, "question")
	}
	delete(payload, "top_k")

	bodyBytes, _ := json.Marshal(payload)
	c.Request.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	c.Request.ContentLength = int64(len(bodyBytes))
}
