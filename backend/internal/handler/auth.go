package handler

import (
	"errors"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/pkg/alog"
	"github.com/oap/backend-go/internal/service"
)

type AuthHandler struct {
	authService *service.AuthService
}

func NewAuthHandler(authService *service.AuthService) *AuthHandler {
	return &AuthHandler{authService: authService}
}

type LoginRequest struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

func (h *AuthHandler) Login(c *gin.Context) {
	reqID := requestIDFromContext(c)
	meta := authMetadataFromContext(c)
	var req LoginRequest
	_ = c.ShouldBindJSON(&req)
	alog.Authf("[AUTH][%s][login] request received username=%q ip=%q ua=%q", reqID, req.Username, meta.IP, meta.UserAgent)

	result, err := h.authService.Login(req.Username, req.Password, meta)
	if err != nil {
		alog.Authf("[AUTH][%s][login] failed err=%v", reqID, err)
		switch mapAuthError(err) {
		case http.StatusBadRequest:
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		case http.StatusUnauthorized:
			c.JSON(http.StatusUnauthorized, gin.H{"error": "用户名或密码错误"})
		default:
			c.JSON(http.StatusInternalServerError, gin.H{"error": "登录失败: " + err.Error()})
		}
		return
	}
	alog.Authf("[AUTH][%s][login] success user_id=%s", reqID, result.User.ID)

	c.JSON(http.StatusOK, buildAuthResponse(result))
}

func (h *AuthHandler) Me(c *gin.Context) {
	userID, _ := c.Get("user_id")
	displayName, _ := c.Get("user_name")
	roles, _ := c.Get("user_roles")

	c.JSON(http.StatusOK, gin.H{
		"user_id":      userID,
		"display_name": displayName,
		"roles":        roles,
	})
}

func authMetadataFromContext(c *gin.Context) service.AuthMetadata {
	reqID := requestIDFromContext(c)
	ip := c.GetHeader("X-Real-IP")
	if ip == "" {
		ip = c.ClientIP()
	}
	return service.AuthMetadata{
		RequestID: reqID,
		UserAgent: c.GetHeader("User-Agent"),
		IP:        ip,
	}
}

func mapAuthError(err error) int {
	switch {
	case errors.Is(err, service.ErrValidation):
		return http.StatusBadRequest
	case errors.Is(err, service.ErrInvalidCredentials):
		return http.StatusUnauthorized
	default:
		return http.StatusInternalServerError
	}
}

func buildAuthResponse(result *service.LoginResult) gin.H {
	return gin.H{
		"access_token": result.AccessToken,
		"token_type":   result.TokenType,
		"expires_in":   result.ExpiresIn,
		"user": gin.H{
			"id":           result.User.ID,
			"username":     result.User.Username,
			"display_name": result.User.DisplayName,
			"roles":        result.User.Roles,
		},
	}
}

func requestIDFromContext(c *gin.Context) string {
	if cached, ok := c.Get("_auth_req_id"); ok {
		if reqID, okCast := cached.(string); okCast && reqID != "" {
			return reqID
		}
	}
	if reqID := c.GetHeader("X-Request-ID"); reqID != "" {
		c.Set("_auth_req_id", reqID)
		return reqID
	}
	reqID := uuid.NewString()
	c.Set("_auth_req_id", reqID)
	return reqID
}
