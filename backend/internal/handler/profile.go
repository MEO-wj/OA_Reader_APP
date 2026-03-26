package handler

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/service"
)

type profileService interface {
	GetProfile(userID uuid.UUID) (*service.UserProfile, error)
	UpdateProfile(userID uuid.UUID, input service.ProfileUpdateInput) (*service.UserProfile, error)
}

type ProfileHandler struct {
	profileService profileService
	uploadRootDir  string
	publicBaseURL  string
}

type updateProfileRequest struct {
	DisplayName      string   `json:"display_name"`
	ProfileTags      []string `json:"profile_tags"`
	Bio              string   `json:"bio"`
	AvatarURL        string   `json:"avatar_url"`
	ProfileUpdatedAt string   `json:"profile_updated_at"`
}

func NewProfileHandler(profileService profileService, publicBaseURL string) *ProfileHandler {
	return &ProfileHandler{
		profileService: profileService,
		uploadRootDir:  "uploads",
		publicBaseURL:  strings.TrimRight(publicBaseURL, "/"),
	}
}

func NewProfileHandlerWithUploadRoot(profileService profileService, publicBaseURL, uploadRootDir string) *ProfileHandler {
	handler := NewProfileHandler(profileService, publicBaseURL)
	if strings.TrimSpace(uploadRootDir) != "" {
		handler.uploadRootDir = uploadRootDir
	}
	return handler
}

func (h *ProfileHandler) GetProfile(c *gin.Context) {
	userID, ok := userIDFromContext(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "未授权访问"})
		return
	}

	profile, err := h.profileService.GetProfile(userID)
	if err != nil {
		if service.IsProfileNotFound(err) {
			c.JSON(http.StatusNotFound, gin.H{"error": "用户资料不存在"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "获取用户资料失败"})
		return
	}

	profile.AvatarURL = h.toAbsoluteAvatarURL(c, profile.AvatarURL)
	c.JSON(http.StatusOK, profile)
}

func (h *ProfileHandler) UpdateProfile(c *gin.Context) {
	userID, ok := userIDFromContext(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "未授权访问"})
		return
	}

	var req updateProfileRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求参数错误"})
		return
	}

	input := service.ProfileUpdateInput{
		DisplayName: req.DisplayName,
		ProfileTags: req.ProfileTags,
		Bio:         req.Bio,
		AvatarURL:   req.AvatarURL,
	}
	if req.ProfileUpdatedAt != "" {
		updatedAt, err := time.Parse(time.RFC3339, req.ProfileUpdatedAt)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid profile_updated_at"})
			return
		}
		input.ProfileUpdatedAt = updatedAt
	}

	profile, err := h.profileService.UpdateProfile(userID, input)
	if err != nil {
		switch {
		case service.IsProfileNotFound(err):
			c.JSON(http.StatusNotFound, gin.H{"error": "用户资料不存在"})
		case mapAuthError(err) == http.StatusBadRequest:
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": "更新用户资料失败"})
		}
		return
	}

	profile.AvatarURL = h.toAbsoluteAvatarURL(c, profile.AvatarURL)
	c.JSON(http.StatusOK, profile)
}

func (h *ProfileHandler) UploadAvatar(c *gin.Context) {
	userID, ok := userIDFromContext(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "未授权访问"})
		return
	}

	fileHeader, err := c.FormFile("avatar")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "missing avatar file"})
		return
	}

	src, err := fileHeader.Open()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无法读取上传文件"})
		return
	}
	defer src.Close()

	head := make([]byte, 512)
	n, err := io.ReadFull(src, head)
	if err != nil && err != io.ErrUnexpectedEOF {
		c.JSON(http.StatusBadRequest, gin.H{"error": "无法读取上传文件"})
		return
	}

	contentType := http.DetectContentType(head[:n])
	if !strings.HasPrefix(contentType, "image/") {
		c.JSON(http.StatusBadRequest, gin.H{"error": "avatar must be an image"})
		return
	}

	ext := filepath.Ext(fileHeader.Filename)
	if ext == "" {
		ext = imageExtension(contentType)
	}
	fileName := fmt.Sprintf("avatar-%d%s", time.Now().UTC().UnixNano(), ext)
	relativeDir := filepath.Join("avatars", userID.String())
	relativePath := filepath.Join(relativeDir, fileName)
	targetPath := filepath.Join(h.uploadRootDir, relativePath)

	if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "创建上传目录失败"})
		return
	}

	dst, err := os.Create(targetPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "保存头像失败"})
		return
	}
	defer dst.Close()

	if _, err := dst.Write(head[:n]); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "保存头像失败"})
		return
	}
	if _, err := io.Copy(dst, src); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "保存头像失败"})
		return
	}

	avatarPath := "/" + filepath.ToSlash(filepath.Join("uploads", relativePath))
	c.JSON(http.StatusOK, gin.H{
		"avatar_url": h.toAbsoluteAvatarURL(c, avatarPath),
	})
}

func userIDFromContext(c *gin.Context) (uuid.UUID, bool) {
	raw, ok := c.Get("user_id")
	if !ok {
		return uuid.UUID{}, false
	}
	userID, ok := raw.(string)
	if !ok || userID == "" {
		return uuid.UUID{}, false
	}
	parsed, err := uuid.Parse(userID)
	if err != nil {
		return uuid.UUID{}, false
	}
	return parsed, true
}

func imageExtension(contentType string) string {
	switch contentType {
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/webp":
		return ".webp"
	default:
		return ".bin"
	}
}

func (h *ProfileHandler) toAbsoluteAvatarURL(c *gin.Context, avatarURL string) string {
	if avatarURL == "" || !strings.HasPrefix(avatarURL, "/uploads/") {
		return avatarURL
	}

	baseURL := h.publicBaseURL
	if baseURL == "" {
		baseURL = requestBaseURL(c.Request)
	}
	if baseURL == "" {
		return avatarURL
	}
	return baseURL + avatarURL
}

func requestBaseURL(r *http.Request) string {
	if r == nil {
		return ""
	}

	scheme := strings.TrimSpace(r.Header.Get("X-Forwarded-Proto"))
	if scheme == "" {
		if r.TLS != nil {
			scheme = "https"
		} else {
			scheme = "http"
		}
	}

	host := strings.TrimSpace(r.Header.Get("X-Forwarded-Host"))
	if host == "" {
		host = strings.TrimSpace(r.Host)
	}
	if host == "" {
		return ""
	}

	return (&url.URL{Scheme: scheme, Host: host}).String()
}
