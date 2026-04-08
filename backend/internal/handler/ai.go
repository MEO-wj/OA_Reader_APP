package handler

import (
	"bytes"
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
}

func NewAIHandler(aiEndURL string) *AIHandler {
	h := &AIHandler{aiEndURL: aiEndURL}
	h.forward = h.defaultForward
	return h
}

func NewAIHandlerWithForward(forward func(c *gin.Context, path string)) *AIHandler {
	return &AIHandler{forward: forward}
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

func (h *AIHandler) Ask(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	h.proxy(c, "/ask")
}

func (h *AIHandler) ClearMemory(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	h.proxy(c, "/clear_memory")
}

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

func (h *AIHandler) Embed(c *gin.Context) {
	h.proxy(c, "/embed")
}
