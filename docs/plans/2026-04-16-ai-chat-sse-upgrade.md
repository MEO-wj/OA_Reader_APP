# AI 请求并发控制 + /chat 流式升级 + 用户资料注入实施方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 弃用 /ask 端点，全面切换到 /chat SSE 流式；在 Backend 增加 AI 请求队列控制并发；将用户资料（标签、简介）作为模板注入 AI 系统提示词。

**Architecture:** Backend 新增 Channel Worker Pool 控制最大 2 并发 AI 请求；/ask 代理到 /chat 做兼容过渡；Backend 从 DB 查用户资料注入请求体；AI_end 在系统提示词中将用户资料模板与 AI 画像分离渲染；前端改用 SSE 流式消费。

**Tech Stack:** Go (channel + goroutine worker pool), Python FastAPI (StreamingResponse), React Native (react-native-sse / fetch ReadableStream)

---

## Task 1: Backend AI 请求并发队列（Go）

**Files:**
- Create: `backend/internal/handler/ai_queue.go`
- Modify: `backend/internal/handler/ai.go:14-17` (AIHandler 结构体注入 queue)
- Modify: `backend/cmd/server/main.go:43` (初始化 queue)
- Test: `backend/internal/handler/ai_queue_test.go`

### Step 1: 写失败测试

```go
// backend/internal/handler/ai_queue_test.go
package handler

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

func TestAIRequestQueue_ProcessesUpToMaxConcurrent(t *testing.T) {
	queue := NewAIRequestQueue(2)
	defer queue.Close()

	var running atomic.Int32
	var maxRunning atomic.Int32
	var completed atomic.Int32
	total := 6

	for i := 0; i < total; i++ {
		go func() {
			queue.Enqueue(context.Background(), func(ctx context.Context) {
				cur := running.Add(1)
				for {
					old := maxRunning.Load()
					if cur <= old || maxRunning.CompareAndSwap(old, cur) {
						break
					}
				}
				time.Sleep(50 * time.Millisecond) // 模拟耗时请求
				running.Add(-1)
				completed.Add(1)
			})
		}
	}

	queue.WaitAll()

	if completed.Load() != int32(total) {
		t.Fatalf("expected %d completed, got %d", total, completed.Load())
	}
	if maxRunning.Load() > 2 {
		t.Fatalf("expected max concurrent <= 2, got %d", maxRunning.Load())
	}
}

func TestAIRequestQueue_ProcessesInFIFOOrder(t *testing.T) {
	queue := NewAIRequestQueue(1) // 单 worker 确保 FIFO 可观测
	defer queue.Close()

	var order []int
	var mu sync.Mutex

	for i := 0; i < 5; i++ {
		i := i
		queue.Enqueue(context.Background(), func(ctx context.Context) {
			mu.Lock()
			order = append(order, i)
			mu.Unlock()
		})
	}

	queue.WaitAll()

	for i, v := range order {
		if v != i {
			t.Fatalf("expected order %d, got %d at index %d", i, v, i)
		}
	}
}

func TestAIRequestQueue_ContextCancellation(t *testing.T) {
	queue := NewAIRequestQueue(1)
	defer queue.Close()

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // 立即取消

	executed := false
	queue.Enqueue(ctx, func(ctx context.Context) {
		executed = true
	})

	// 给 worker 时间处理
	time.Sleep(50 * time.Millisecond)

	// 任务应该被跳过（context 已取消）
	if executed {
		t.Fatal("expected task to be skipped due to context cancellation")
	}
}
```

### Step 2: 运行测试验证失败

Run: `cd backend && go test ./internal/handler/ -run TestAIRequestQueue -v`
Expected: FAIL — `NewAIRequestQueue` 未定义

### Step 3: 实现 AIRequestQueue

```go
// backend/internal/handler/ai_queue.go
package handler

import (
	"context"
	"sync"
)

// queuedRequest 代表一个排队的 AI 请求
type queuedRequest struct {
	ctx    context.Context
	execute func(ctx context.Context)
	done   chan struct{}
}

// AIRequestQueue 控制并发 AI 请求的 FIFO 队列
type AIRequestQueue struct {
	ch      chan *queuedRequest
	workers int
	wg      sync.WaitGroup
	closeCh chan struct{}
}

// NewAIRequestQueue 创建一个最大 maxConcurrent 并发的请求队列
func NewAIRequestQueue(maxConcurrent int) *AIRequestQueue {
	q := &AIRequestQueue{
		ch:      make(chan *queuedRequest, 50), // 50 缓冲防 OOM
		workers: maxConcurrent,
		closeCh: make(chan struct{}),
	}
	for i := 0; i < q.workers; i++ {
		q.wg.Add(1)
		go q.worker()
	}
	return q
}

func (q *AIRequestQueue) worker() {
	defer q.wg.Done()
	for {
		select {
		case req, ok := <-q.ch:
			if !ok {
				return
			}
			// 检查 context 是否已取消
			select {
			case <-req.ctx.Done():
				close(req.done)
			default:
				req.execute(req.ctx)
				close(req.done)
			}
		case <-q.closeCh:
			return
		}
	}
}

// Enqueue 将请求加入队列，返回一个 channel 在请求完成后关闭
func (q *AIRequestQueue) Enqueue(ctx context.Context, execute func(ctx context.Context)) <-chan struct{} {
	done := make(chan struct{})
	select {
	case q.ch <- &queuedRequest{ctx: ctx, execute: execute, done: done}:
	case <-ctx.Done():
		close(done)
	case <-q.closeCh:
		close(done)
	}
	return done
}

// WaitAll 等待队列中所有已入队的任务完成
func (q *AIRequestQueue) WaitAll() {
	// 关闭 ch 让 worker drain 完
	close(q.ch)
	q.wg.Wait()
}

// Close 关闭队列（不再接受新任务）
func (q *AIRequestQueue) Close() {
	select {
	case <-q.closeCh:
		// 已关闭
	default:
		close(q.closeCh)
	}
}
```

### Step 4: 运行测试

Run: `cd backend && go test ./internal/handler/ -run TestAIRequestQueue -v`
Expected: PASS

> **注意：** `WaitAll` 目前会关闭 channel，后续需改为在生产环境中不调用 `WaitAll`，而是让 queue 生命周期跟随 server。在 main.go 的 graceful shutdown 中调用 `Close()` 即可。如果测试需要不关闭的版本，可后续调整为 `WaitDrain()` 方法。当前测试通过后，在 Task 4 中会集成到 handler 层，届时再做生命周期调整。

### Step 5: 提交

```bash
git add backend/internal/handler/ai_queue.go backend/internal/handler/ai_queue_test.go
git commit -m "feat(backend): add AI request queue with FIFO and concurrency control"
```

---

## Task 2: Backend AIHandler 集成队列 + 用户资料注入

**Files:**
- Modify: `backend/internal/handler/ai.go:14-86` (AIHandler 结构体和 injectUserID)
- Modify: `backend/cmd/server/main.go:37-43,82-88` (初始化 queue + 路由)
- Test: `backend/internal/handler/ai_test.go`

### Step 1: 写失败测试

在 `ai_test.go` 中新增测试，验证：
1. 新增的 `/chat` 路由代理到 AI_end `/chat`
2. 用户资料被注入到转发 body 中

```go
// 追加到 backend/internal/handler/ai_test.go

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
	// 验证原始字段保留
	if gotBody["message"] != "hello" {
		t.Fatalf("expected message=hello, got %v", gotBody["message"])
	}
}

func TestAsk_ProxiesToChatEndpoint(t *testing.T) {
	gin.SetMode(gin.TestMode)

	var gotPath string
	h := NewAIHandlerWithForward(func(c *gin.Context, path string) {
		gotPath = path
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	r := gin.New()
	r.POST("/api/ai/ask", func(c *gin.Context) {
		c.Set("user_id", "user-123")
		h.Ask(c)
	})

	req := httptest.NewRequest(http.MethodPost, "/api/ai/ask",
		io.NopCloser(bytes.NewBufferString(`{"question":"hi"}`)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	// /ask 应代理到 /chat（兼容过渡）
	if gotPath != "/chat" {
		t.Fatalf("expected /ask to proxy to /chat, got %s", gotPath)
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
			"profile_tags": []string{"计算机", "夜猫子"},
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
```

### Step 2: 运行测试验证失败

Run: `cd backend && go test ./internal/handler/ -run "TestChat_ProxiesToChat|TestAsk_ProxiesToChat|TestInjectUserProfile" -v`
Expected: FAIL — `Chat` 方法未定义，`injectUserProfile` 未定义

### Step 3: 修改 AIHandler 集成队列和用户资料

```go
// backend/internal/handler/ai.go (完整重写)
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

// Chat 处理 /chat 请求：注入 user_id + 用户资料 → 入队 → 代理
func (h *AIHandler) Chat(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	injectUserProfile(c)
	h.queuedProxy(c, "/chat")
}

// Ask 兼容端点：字段映射 question→message 后代理到 /chat
func (h *AIHandler) Ask(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	// 字段映射：旧 ask 格式 → chat 格式
	remapAskToChat(c)
	injectUserProfile(c)
	h.queuedProxy(c, "/chat")
}

// ClearMemory 保留原有逻辑（不走队列，低频操作）
func (h *AIHandler) ClearMemory(c *gin.Context) {
	if !injectUserID(c) {
		return
	}
	h.proxy(c, "/clear_memory")
}

func (h *AIHandler) Embed(c *gin.Context) {
	h.proxy(c, "/embed")
}

// queuedProxy 将请求放入队列，控制并发
func (h *AIHandler) queuedProxy(c *gin.Context, path string) {
	done := h.queue.Enqueue(c.Request.Context(), func(ctx context.Context) {
		h.forward(c, path)
	})
	<-done
}

// injectUserID 从 JWT context 注入 user_id 到请求体
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

// injectUserProfile 从 context 中获取用户资料注入到请求体
// 资料由 middleware 或 handler 在调用前从 DB 查询并写入 context
func injectUserProfile(c *gin.Context) {
	profile, ok := c.Get("user_profile")
	if !ok {
		return
	}
	profileMap, ok := profile.(map[string]interface{})
	if !ok {
		return
	}

	// 读取当前 body，注入 profile 字段
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
	if tags, ok := profileMap["profile_tags"].([]interface{}); ok && len(tags) > 0 {
		payload["profile_tags"] = tags
	}
	if bio, ok := profileMap["bio"].(string); ok && bio != "" {
		payload["bio"] = bio
	}

	bodyBytes, _ := json.Marshal(payload)
	c.Request.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	c.Request.ContentLength = int64(len(bodyBytes))
}

// remapAskToChat 将旧 /ask 请求字段映射为 /chat 格式
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

	// question → message
	if q, ok := payload["question"]; ok {
		payload["message"] = q
		delete(payload, "question")
	}
	// 删除 top_k（不再需要）
	delete(payload, "top_k")
	// display_name 保留（如果前端传了），后面会被 injectUserProfile 覆盖

	bodyBytes, _ := json.Marshal(payload)
	c.Request.Body = io.NopCloser(bytes.NewReader(bodyBytes))
	c.Request.ContentLength = int64(len(bodyBytes))
}
```

### Step 4: 新增用户资料查询中间件

需要一个 middleware 在 AI 路由组上，从 DB 查用户资料写入 context。

```go
// backend/internal/middleware/profile.go
package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/service"
)

// InjectProfile 从 DB 查询用户资料并写入 context，供 AI handler 使用
func InjectProfile(profileService *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userIDStr, ok := c.Get("user_id")
		if !ok {
			c.Next()
			return
		}
		userID, err := uuid.Parse(userIDStr.(string))
		if err != nil {
			c.Next()
			return
		}
		profile, err := profileService.GetProfile(userID)
		if err != nil {
			// 查不到 profile 不阻塞请求
			c.Next()
			return
		}
		profileData := map[string]interface{}{
			"display_name": profile.DisplayName,
			"profile_tags": profile.ProfileTags,
			"bio":          profile.Bio,
		}
		c.Set("user_profile", profileData)
		c.Next()
	}
}
```

### Step 5: 修改 main.go 路由注册

```go
// backend/cmd/server/main.go — 修改部分

// 初始化处理器（修改 AIHandler 初始化）
aiQueue := handler.NewAIRequestQueue(2)
defer aiQueue.Close()
aiHandler := handler.NewAIHandler(cfg.AIEndURL, aiQueue)

// ... (在路由注册处修改)

// AI 路由 (需要认证)
ai := r.Group("/api/ai")
ai.Use(middleware.AuthRequired(cfg.AuthJWTSecret))
ai.Use(middleware.InjectProfile(profileService)) // 新增：注入用户资料
{
    ai.POST("/chat", aiHandler.Chat)              // 新增：原生 SSE 端点
    ai.POST("/ask", aiHandler.Ask)               // 保留：兼容过渡，内部代理到 /chat
    ai.POST("/clear_memory", aiHandler.ClearMemory)
    ai.POST("/embed", aiHandler.Embed)
}
```

### Step 6: 运行全部 AI handler 测试

Run: `cd backend && go test ./internal/handler/ -v`
Expected: 全部 PASS（包含旧测试 + 新测试）

### Step 7: 提交

```bash
git add backend/internal/handler/ai.go backend/internal/handler/ai_test.go backend/internal/middleware/profile.go backend/cmd/server/main.go
git commit -m "feat(backend): integrate AI queue, add /chat route, inject user profile into AI requests"
```

---

## Task 3: AI_end 扩展 ChatRequest 支持用户资料

**Files:**
- Modify: `ai_end/src/api/models.py:9-14` (ChatRequest 新增字段)
- Test: `ai_end/tests/unit/test_chat_models.py`（新建）

### Step 1: 写失败测试

```python
# ai_end/tests/unit/test_chat_models.py
"""ChatRequest 模型测试"""
import pytest
from pydantic import ValidationError
from src.api.models import ChatRequest


class TestChatRequest:
    def test_basic_fields_required(self):
        """message 和 user_id 必填"""
        with pytest.raises(ValidationError):
            ChatRequest()

    def test_basic_fields_valid(self):
        req = ChatRequest(message="hello", user_id="550e8400-e29b-41d4-a716-446655440000")
        assert req.message == "hello"
        assert req.user_id == "550e8400-e29b-41d4-a716-446655440000"
        assert req.conversation_id is None
        assert req.display_name is None
        assert req.profile_tags is None
        assert req.bio is None

    def test_profile_fields_optional(self):
        req = ChatRequest(
            message="hi",
            user_id="550e8400-e29b-41d4-a716-446655440000",
            display_name="张三",
            profile_tags=["计算机", "夜猫子"],
            bio="大三学生",
            conversation_id="conv-1",
        )
        assert req.display_name == "张三"
        assert req.profile_tags == ["计算机", "夜猫子"]
        assert req.bio == "大三学生"
        assert req.conversation_id == "conv-1"

    def test_profile_tags_empty_list_ok(self):
        req = ChatRequest(
            message="hi",
            user_id="550e8400-e29b-41d4-a716-446655440000",
            profile_tags=[],
        )
        assert req.profile_tags == []

    def test_invalid_uuid_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", user_id="not-a-uuid")
```

### Step 2: 运行测试验证失败

Run: `cd ai_end && uv run pytest tests/unit/test_chat_models.py -v`
Expected: FAIL — `profile_tags`, `bio`, `display_name` 字段不存在

### Step 3: 修改 ChatRequest 模型

```python
# ai_end/src/api/models.py — 修改 ChatRequest
class ChatRequest(BaseModel):
    """聊天请求"""

    message: str
    user_id: str = Field(min_length=1, max_length=64)
    conversation_id: str | None = None
    # 用户资料字段（由 Backend 从 users 表查询后注入）
    display_name: str | None = None
    profile_tags: list[str] | None = None
    bio: str | None = None

    @field_validator("user_id")
    @classmethod
    def _validate_user_id_uuid(cls, v: str) -> str:
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc
```

### Step 4: 运行测试

Run: `cd ai_end && uv run pytest tests/unit/test_chat_models.py -v`
Expected: PASS

### Step 5: 提交

```bash
git add ai_end/src/api/models.py ai_end/tests/unit/test_chat_models.py
git commit -m "feat(ai_end): extend ChatRequest with user profile fields"
```

---

## Task 4: AI_end 用户资料模板注入系统提示词

**Files:**
- Modify: `ai_end/src/chat/prompts_runtime.py:3-23` (SYSTEM_PROMPT_TEMPLATE 新增模板区域)
- Modify: `ai_end/src/chat/client.py:787-801` (画像注入逻辑拆分为两层)
- Modify: `ai_end/src/api/chat_service.py:13-17,33-41` (传递用户资料到 ChatClient)
- Modify: `ai_end/src/di/providers.py:74-83,85-92` (传递参数)
- Modify: `ai_end/src/api/main.py:121-144` (传递 ChatRequest 字段)
- Test: `ai_end/tests/unit/test_user_profile_template.py`（新建）

### Step 1: 写失败测试

```python
# ai_end/tests/unit/test_user_profile_template.py
"""用户资料模板注入测试"""
import pytest
from src.chat.prompts_runtime import build_user_profile_section


class TestUserProfileSection:
    def test_full_profile(self):
        result = build_user_profile_section(
            display_name="张三",
            profile_tags=["计算机", "夜猫子"],
            bio="计算机学院大三学生",
        )
        assert "【用户资料】" in result
        assert "张三" in result
        assert "计算机" in result
        assert "夜猫子" in result
        assert "大三学生" in result

    def test_empty_profile_returns_empty(self):
        result = build_user_profile_section(
            display_name=None,
            profile_tags=None,
            bio=None,
        )
        assert result == ""

    def test_partial_profile_name_only(self):
        result = build_user_profile_section(display_name="李四")
        assert "李四" in result
        assert "兴趣标签" not in result  # 没有标签就不显示这一行

    def test_partial_profile_tags_only(self):
        result = build_user_profile_section(
            profile_tags=["摄影", "阅读"],
        )
        assert "摄影" in result
        assert "阅读" in result
        assert "昵称" not in result  # 没有名字就不显示这一行

    def test_empty_tags_list_returns_empty(self):
        result = build_user_profile_section(
            display_name="测试",
            profile_tags=[],
        )
        assert "兴趣标签" not in result
```

### Step 2: 运行测试验证失败

Run: `cd ai_end && uv run pytest tests/unit/test_user_profile_template.py -v`
Expected: FAIL — `build_user_profile_section` 不存在

### Step 3: 实现用户资料模板构建函数

在 `ai_end/src/chat/prompts_runtime.py` 中新增：

```python
# 追加到 ai_end/src/chat/prompts_runtime.py 末尾

# ─── 用户资料模板 ─────────────────────────────────────

def build_user_profile_section(
    display_name: str | None = None,
    profile_tags: list[str] | None = None,
    bio: str | None = None,
) -> str:
    """构建用户资料提示词区块。

    用户手动填写的资料与 AI 画像分离，每次从 DB 实时读取，
    用户修改后即时生效，不写入 AI 画像表。

    Returns:
        格式化的用户资料文本，所有字段为空时返回空字符串。
    """
    lines: list[str] = []

    if display_name:
        lines.append(f"昵称：{display_name}")

    if profile_tags:
        tags_str = "、".join(profile_tags)
        lines.append(f"兴趣标签：{tags_str}")

    if bio:
        lines.append(f"个人简介：{bio}")

    if not lines:
        return ""

    return "【用户资料】\n" + "\n".join(lines)
```

### Step 4: 修改系统提示词模板

修改 `SYSTEM_PROMPT_TEMPLATE`，在 `{profile_section}` 前增加 `{user_profile_section}`：

```python
# ai_end/src/chat/prompts_runtime.py — 修改 SYSTEM_PROMPT_TEMPLATE
SYSTEM_PROMPT_TEMPLATE = """你是一个智能校园 OA 助手，善于理解用户需求并提供帮助。
当前日期：{current_date}（{weekday}）

【可用技能】
{skills_list}

【执行框架】
你必须调用任务执行框架（todolist），它会引导你按步骤完成每次对话。请严格遵循其指令，不可跳过步骤。

【用户画像分层约束】
- 用户画像分为 confirmed（已确认）和 hypothesized（推测）两层，hypothesized 内容仅供参考，不可当作已确认事实
- 禁止将 hypothesized 推测合并写入 confirmed 已确认层

【输出约束】
- 当返回多条数据时，优先使用 Markdown 表格展示
- 仅输出最终结论与必要依据，证据不足时简洁说明"当前证据不足"
- 不要暴露内部工具调用过程，不提及工具名、调用参数等实现细节
- 信息不足时先说明不确定性，再给合理的建议方案，禁用承诺性表述

{user_profile_section}
【数据库保存的用户画像】
{profile_section}"""
```

> **设计要点：** `{user_profile_section}` 在 `{profile_section}` 之前。用户资料是用户自己填写的确定性信息，优先级高于 AI 推测画像。当 `user_profile_section` 为空字符串时，对提示词无影响。

### Step 5: 修改 ChatClient 支持接收用户资料

ChatClient 的 `_build_system_prompt` 需要接受 `user_profile` 参数：

```python
# ai_end/src/chat/client.py — _build_system_prompt 方法签名修改
# 找到 _build_system_prompt 方法，修改签名和调用

def _build_system_prompt(
    self,
    portrait: str = "",
    knowledge: str = "",
    user_profile: str = "",  # 新增参数
) -> str:
    """构建系统提示词"""
    from src.chat.prompts_runtime import (
        SYSTEM_PROMPT_TEMPLATE,
        build_user_profile_section,
    )

    # ... (现有 skills_list 构建逻辑不变)

    profile_section = self._format_profile_section(portrait, knowledge)

    return SYSTEM_PROMPT_TEMPLATE.format(
        current_date=current_date_str,
        weekday=weekday_str,
        skills_list=skills_list,
        user_profile_section=user_profile,  # 新增
        profile_section=profile_section,
    )
```

### Step 6: 修改画像注入逻辑（chat_stream_async 第 787-801 行）

将用户资料模板注入与 AI 画像注入合并：

```python
# ai_end/src/chat/client.py — chat_stream_async 中画像注入部分修改

# 仅在新会话首次请求时加载画像
if is_new_runtime_session and history_empty and self.user_id:
    profile = await self._history_manager.memory_db.get_profile(self.user_id)
    if profile:
        profile_loaded = True
        portrait = self._sanitize_memory_text(str(profile.get("portrait_text", "") or ""))
        knowledge = self._sanitize_memory_text(str(profile.get("knowledge_text", "") or ""))
        portrait_len = len(str(portrait or ""))
        knowledge_len = len(str(knowledge or ""))

    # 构建用户资料模板（来自请求参数，非画像表）
    user_profile_text = ""
    if self.user_profile:
        user_profile_text = build_user_profile_section(**self.user_profile)

    if portrait or knowledge or user_profile_text:
        main_prompt = self._build_system_prompt(
            portrait=portrait,
            knowledge=knowledge,
            user_profile=user_profile_text,
        )
        self.messages[0]["content"] = main_prompt
        profile_injected = True
```

### Step 7: 修改 ChatClient 接收和存储 user_profile

```python
# ai_end/src/chat/client.py — __init__ 或 create 方法中新增 user_profile 参数

class ChatClient:
    def __init__(self, config, user_id=None, conversation_id=None, user_profile=None):
        # ... 现有代码 ...
        self.user_profile = user_profile  # {"display_name": ..., "profile_tags": [...], "bio": ...}

    @classmethod
    async def create(cls, config, user_id=None, conversation_id=None, user_profile=None):
        instance = cls(config, user_id, conversation_id, user_profile)
        # ... 现有初始化逻辑 ...
        return instance
```

### Step 8: 修改 ChatService 传递用户资料

```python
# ai_end/src/api/chat_service.py — 修改 ChatService

class ChatService:
    def __init__(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
        user_profile: dict | None = None,  # 新增
    ) -> None:
        self.config = Config.load()
        self._client = None
        self.user_id = self._normalize_user_id(user_id)
        self.conversation_id = conversation_id or "default"
        self.user_profile = user_profile  # 新增

    async def _get_client(self):
        if self._client is None:
            await self._ensure_user_memory_ready()
            self._client = await create_chat_client(
                self.config,
                self.user_id,
                self.conversation_id,
                user_profile=self.user_profile,  # 新增
            )
        return self._client
```

### Step 9: 修改 providers.py 和 main.py 传递参数

```python
# ai_end/src/di/providers.py — 修改 create_chat_client 和 get_chat_service

async def create_chat_client(config, user_id=None, conversation_id=None, user_profile=None):
    from src.chat.client import ChatClient
    return await ChatClient.create(config, user_id, conversation_id, user_profile=user_profile)

def get_chat_service(user_id=None, conversation_id=None, user_profile=None):
    from src.api.chat_service import ChatService
    return ChatService(user_id=user_id, conversation_id=conversation_id, user_profile=user_profile)
```

```python
# ai_end/src/api/main.py — 修改 /chat 端点

@app.post("/chat", response_class=StreamingResponse)
async def chat(request: ChatRequest) -> StreamingResponse:
    from src.db.memory import MemoryDB
    db = MemoryDB()
    conversation_id, _title = await db.get_or_create_session(
        request.user_id, request.conversation_id,
    )

    # 收集用户资料（仅在有数据时传递）
    user_profile = None
    if request.display_name or request.profile_tags or request.bio:
        user_profile = {
            "display_name": request.display_name,
            "profile_tags": request.profile_tags,
            "bio": request.bio,
        }

    service = get_chat_service(
        user_id=request.user_id,
        conversation_id=conversation_id,
        user_profile=user_profile,
    )
    return StreamingResponse(
        service.chat_stream(request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": conversation_id,
        },
    )
```

### Step 10: 运行测试

Run: `cd ai_end && uv run pytest tests/unit/test_user_profile_template.py tests/unit/test_chat_models.py -v`
Expected: 全部 PASS

### Step 11: 运行现有 AI_end 测试确保不回归

Run: `cd ai_end && uv run pytest tests/unit/ -v`
Expected: 全部 PASS（可能需要调整 `_build_system_prompt` 的现有调用处）

### Step 12: 提交

```bash
git add ai_end/src/chat/prompts_runtime.py ai_end/src/chat/client.py ai_end/src/api/chat_service.py ai_end/src/di/providers.py ai_end/src/api/main.py ai_end/src/api/models.py ai_end/tests/unit/test_user_profile_template.py ai_end/tests/unit/test_chat_models.py
git commit -m "feat(ai_end): inject user profile template into system prompt, separate from AI portrait"
```

---

## Task 5: 前端改用 SSE 流式消费（OAP-app）

**Files:**
- Modify: `OAP-app/services/ai.ts` (新增 `chatSSE` 函数)
- Modify: `OAP-app/hooks/use-ai-chat.ts` (改用流式)
- Modify: `OAP-app/types/chat.ts` (ChatMessage 新增流式状态)
- Test: 手动测试（前端暂无自动化测试框架）

### Step 1: 修改 ChatMessage 类型

```typescript
// OAP-app/types/chat.ts
import type { RelatedArticle } from '@/types/article';

export type ChatMessage = {
  id: string;
  isUser: boolean;
  text: string;
  isStreaming?: boolean;       // 新增：是否正在流式输出
  highlights?: string[];
  related?: RelatedArticle[];
};
```

### Step 2: 新增 SSE 流式请求函数

```typescript
// OAP-app/services/ai.ts — 新增 chatSSE 函数

export type SSEEvent = {
  type: string;
  [key: string]: unknown;
};

/**
 * SSE 流式聊天请求。
 * 使用 fetch ReadableStream 消费 SSE 事件（React Native 和 Web 通用）。
 */
export async function chatSSE(
  message: string,
  token: string,
  conversationId?: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Error) => void,
): Promise<void> {
  const resp = await fetch(`${getApiBaseUrl()}/ai/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      message,
      conversation_id: conversationId || undefined,
    }),
  });

  if (!resp.ok) {
    let errorMsg = '当前服务不可用，请稍后再试。';
    if (resp.status === 503) errorMsg = '服务繁忙，请稍后再试';
    else if (resp.status === 401) errorMsg = '登录已过期，请重新登录';
    onError?.(new Error(errorMsg));
    return;
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    onError?.(new Error('无法读取响应流'));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 解析 SSE 事件（event: xxx\ndata: yyy\n\n）
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const eventBlock of events) {
        const lines = eventBlock.split('\n');
        let eventType = 'message';
        let dataStr = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            dataStr = line.slice(6);
          }
        }

        if (!dataStr) continue;

        try {
          const data = JSON.parse(dataStr);
          onEvent({ type: eventType, ...data });
        } catch {
          // 忽略无法解析的 data
        }
      }
    }
  } catch (err) {
    onError?.(err instanceof Error ? err : new Error('连接中断'));
  }
}
```

> **注意：** 已安装的 `react-native-sse` 也可用于此，但 fetch ReadableStream 是更通用的方案（Web/Android/iOS 三端兼容），且不需要额外依赖。如遇特定平台问题再切换到 `react-native-sse`。

### Step 3: 修改 use-ai-chat hook 改用流式

```typescript
// OAP-app/hooks/use-ai-chat.ts — 重写 sendChat

import { useCallback, useEffect, useRef, useState } from 'react';

import type { RelatedArticle } from '@/types/article';
import { chatSSE, clearAiMemory } from '@/services/ai';
import { clearChatHistory, getChatHistory, setChatHistory } from '@/storage/chat-storage';
import type { ChatMessage } from '@/types/chat';
import { extractKeywords } from '@/utils/text';

export function useAiChat(token?: string | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const [conversationId, setConversationId] = useState<string>();
  const abortRef = useRef(false); // 用于组件卸载时中断

  useEffect(() => {
    let mounted = true;
    getChatHistory().then((history) => {
      if (!mounted) return;
      if (history && history.length > 0) setMessages(history);
      setIsHydrated(true);
    });
    return () => {
      mounted = false;
      abortRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    void setChatHistory(messages);
  }, [isHydrated, messages]);

  const setMessageText = useCallback((id: string, text: string) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, text } : item)));
  }, []);

  const updateRelated = useCallback((id: string, related: RelatedArticle[]) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, related } : item)));
  }, []);

  const setStreaming = useCallback((id: string, isStreaming: boolean) => {
    setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, isStreaming } : item)));
  }, []);

  const sendChat = useCallback(
    async (question: string) => {
      if (!question.trim() || isThinking) return;
      const highlights = extractKeywords(question);

      const userMessage: ChatMessage = {
        id: `u-${Date.now()}`,
        isUser: true,
        text: question,
      };
      const aiMessageId = `a-${Date.now()}`;
      const aiMessage: ChatMessage = {
        id: aiMessageId,
        isUser: false,
        text: '',
        isStreaming: true,
        highlights,
      };
      setMessages((prev) => [...prev, userMessage, aiMessage]);
      setIsThinking(true);
      abortRef.current = false;

      let fullText = '';
      let relatedArticles: RelatedArticle[] = [];

      await chatSSE(
        question,
        token || '',
        conversationId,
        (event) => {
          if (abortRef.current) return;

          if (event.type === 'start') {
            const convId = (event as { conversation_id?: string }).conversation_id;
            if (convId) setConversationId(convId);
          } else if (event.type === 'delta') {
            const content = (event as { content?: string }).content || '';
            fullText += content;
            setMessageText(aiMessageId, fullText);
          } else if (event.type === 'tool_result') {
            // 从 search_articles 结果中提取 related articles
            const tool = (event as { tool?: string }).tool;
            if (tool === 'search_articles') {
              try {
                const result = JSON.parse((event as { result?: string }).result || '[]');
                if (Array.isArray(result)) {
                  relatedArticles = result
                    .slice(0, 5)
                    .map((doc: Record<string, unknown>) => ({
                      id: doc.id as number,
                      title: (doc.title as string) || '',
                      unit: doc.unit as string | undefined,
                      published_on: doc.published_on as string | undefined,
                      summary_snippet: doc.summary_snippet as string | undefined,
                    }));
                }
              } catch {
                // 解析失败忽略
              }
            }
          } else if (event.type === 'done') {
            setStreaming(aiMessageId, false);
            if (relatedArticles.length > 0) {
              updateRelated(aiMessageId, relatedArticles);
            }
            setIsThinking(false);
          } else if (event.type === 'error') {
            const msg = (event as { message?: string }).message;
            if (!fullText) {
              setMessageText(aiMessageId, msg || '抱歉，当前服务不可用，请稍后再试。');
            }
            setStreaming(aiMessageId, false);
            setIsThinking(false);
          }
        },
        (error) => {
          if (abortRef.current) return;
          const errorMsg = error.message === 'missing token'
            ? '登录已过期，请重新登录。'
            : error.message;
          setMessageText(aiMessageId, errorMsg);
          setStreaming(aiMessageId, false);
          setIsThinking(false);
        },
      );
    },
    [conversationId, isThinking, setMessageText, setStreaming, token, updateRelated],
  );

  const clearChat = useCallback(async () => {
    setMessages([]);
    setIsThinking(false);
    setConversationId(undefined);
    if (token) {
      try { await clearAiMemory(token); } catch { /* ignore */ }
    }
    await clearChatHistory();
  }, [token]);

  return {
    messages,
    isThinking,
    sendChat,
    setMessages,
    clearChat,
  };
}
```

> **注意：** `displayName` 参数已从 hook 中移除。Backend 自动从 DB 注入用户资料，前端不再需要传递。

### Step 4: 检查调用方是否需要调整

搜索 `useAiChat` 的使用处，确认 `displayName` 参数移除后不会报错：

```bash
cd OAP-app && grep -rn "useAiChat" --include="*.ts" --include="*.tsx"
```

如果调用方传了 `displayName`，移除即可（TypeScript 会提示多余参数）。

### Step 5: 手动测试

1. 启动 AI_end: `cd ai_end && uv run uvicorn src.api.main:app --host 0.0.0.0 --port 4421`
2. 启动 Backend: `cd backend && go run cmd/server/main.go`
3. 启动前端: `cd OAP-app && npm run web`
4. 登录 → 打开 AI 聊天 → 发送消息
5. 验证：
   - 消息逐字显示（流式效果）
   - 工具调用后能展示相关文章
   - 新会话自动管理 conversation_id
   - 服务端返回 `X-Conversation-Id` header

### Step 6: 提交

```bash
git add OAP-app/services/ai.ts OAP-app/hooks/use-ai-chat.ts OAP-app/types/chat.ts
git commit -m "feat(app): switch AI chat from /ask JSON to /chat SSE streaming"
```

---

## Task 6: 清理废弃代码

**Files:**
- Modify: `ai_end/src/api/main.py:242-260` (标记 /ask 弃用或删除)
- Modify: `ai_end/src/api/compat_service.py` (删除 ask 方法和 build_runtime_hints)
- Modify: `ai_end/src/api/compat_models.py` (删除 AskCompatRequest)
- Delete: `ai_end/tests/integration/test_compat_endpoints.py` 中的 /ask 相关测试
- Modify: `ai_end/tests/unit/test_compat_service.py` (删除 ask 相关测试)
- Modify: `backend/internal/handler/ai.go` (如果确认可移除 Ask 方法，则删除)

### Step 1: AI_end — 删除 /ask 端点

在 `ai_end/src/api/main.py` 中删除 `ask_compat` 函数及其 `@app.post("/ask")` 路由。

### Step 2: AI_end — 清理 CompatService

从 `ai_end/src/api/compat_service.py` 中删除：
- `build_runtime_hints()` 函数
- `ask()` 方法
- `_aggregate_events()` 方法
- `_normalize_tool_result_to_docs()` 方法
- `_dedupe_and_aggregate_docs()` 方法

保留 `clear_memory` 和 `embed` 相关方法（它们仍然需要 CompatService）。

### Step 3: AI_end — 清理 compat_models

从 `ai_end/src/api/compat_models.py` 中删除 `AskCompatRequest` 类。

### Step 4: AI_end — 清理测试

删除 `ai_end/tests/unit/test_compat_service.py` 中与 `ask` 和 `build_runtime_hints` 相关的测试用例。
删除 `ai_end/tests/integration/test_compat_endpoints.py` 中 `/ask` 相关测试。

### Step 5: Backend — 评估是否删除 /ask 路由

如果确认所有客户端（Web、App）都已切换到 `/chat`，可删除：
- `ai.POST("/ask", aiHandler.Ask)` 路由
- `Ask` handler 方法
- `remapAskToChat` 函数

**建议：** 本版本保留 `/ask` → `/chat` 的代理过渡一个版本周期，确认无客户端使用后再删除。

### Step 6: 运行全部测试

```bash
cd ai_end && uv run pytest tests/ -v
cd backend && go test ./... -v
```

### Step 7: 提交

```bash
git add ai_end/ backend/
git commit -m "chore: remove deprecated /ask endpoint and compat service ask logic"
```

---

## 实施顺序总结

| 顺序 | Task | 依赖 | 模块 |
|------|------|------|------|
| 1 | AI 请求并发队列 | 无 | Backend |
| 2 | Handler 集成队列 + 用户资料注入 | Task 1 | Backend |
| 3 | ChatRequest 扩展 | 无 | AI_end |
| 4 | 用户资料模板注入提示词 | Task 3 | AI_end |
| 5 | 前端 SSE 流式 | Task 2（需要 /chat 路由） | OAP-app |
| 6 | 清理废弃代码 | Task 2, 4, 5 | AI_end + Backend |

> Task 1 和 Task 3 可以并行。Task 2 依赖 Task 1。Task 4 依赖 Task 3。Task 5 依赖 Task 2。Task 6 最后做。
