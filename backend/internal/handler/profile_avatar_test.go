package handler

import (
	"bytes"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
)

func TestUploadAvatar_RejectsMissingFile(t *testing.T) {
	gin.SetMode(gin.TestMode)

	h := NewProfileHandler(&fakeProfileService{}, "")
	h.uploadRootDir = t.TempDir()
	r := gin.New()
	r.POST("/api/user/profile/avatar", func(c *gin.Context) {
		c.Set("user_id", uuid.New().String())
		h.UploadAvatar(c)
	})

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	_ = writer.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/user/profile/avatar", body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestUploadAvatar_RejectsNonImageFile(t *testing.T) {
	gin.SetMode(gin.TestMode)

	h := NewProfileHandler(&fakeProfileService{}, "")
	h.uploadRootDir = t.TempDir()
	r := gin.New()
	r.POST("/api/user/profile/avatar", func(c *gin.Context) {
		c.Set("user_id", uuid.New().String())
		h.UploadAvatar(c)
	})

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	part, err := writer.CreateFormFile("avatar", "avatar.txt")
	if err != nil {
		t.Fatalf("CreateFormFile: %v", err)
	}
	if _, err := part.Write([]byte("not-an-image")); err != nil {
		t.Fatalf("Write: %v", err)
	}
	_ = writer.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/user/profile/avatar", body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestUploadAvatar_ReturnsAvatarURL(t *testing.T) {
	gin.SetMode(gin.TestMode)

	userID := uuid.New()
	h := NewProfileHandler(&fakeProfileService{}, "")
	h.uploadRootDir = t.TempDir()
	r := gin.New()
	r.POST("/api/user/profile/avatar", func(c *gin.Context) {
		c.Set("user_id", userID.String())
		h.UploadAvatar(c)
	})

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	part, err := writer.CreateFormFile("avatar", "avatar.png")
	if err != nil {
		t.Fatalf("CreateFormFile: %v", err)
	}
	if _, err := part.Write([]byte{137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3, 4}); err != nil {
		t.Fatalf("Write: %v", err)
	}
	_ = writer.Close()

	req := httptest.NewRequest(http.MethodPost, "/api/user/profile/avatar", body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var payload map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	avatarURL := payload["avatar_url"]
	if avatarURL == "" {
		t.Fatal("expected avatar_url in response")
	}
	if got, want := avatarURL[:len("/uploads/")], "/uploads/"; got != want {
		t.Fatalf("expected relative avatar_url prefix %q, got %q", want, avatarURL)
	}

	savedPath := filepath.Join(h.uploadRootDir, avatarURL[len("/uploads/"):])
	if _, err := os.Stat(savedPath); err != nil {
		t.Fatalf("expected uploaded file to exist: %v", err)
	}
}
