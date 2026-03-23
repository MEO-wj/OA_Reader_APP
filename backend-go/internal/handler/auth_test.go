package handler

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/config"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/repository"
	"github.com/oap/backend-go/internal/service"
)

type handlerAuthRepoStub struct {
	session *model.Session
}

func (s *handlerAuthRepoStub) GetCredential(username string) (*repository.UserCredential, error) {
	return nil, repository.ErrNotFound
}

func (s *handlerAuthRepoStub) CreateWithPassword(username, passwordHash, passwordAlgo string, passwordCost int, displayName string) (*model.User, error) {
	return &model.User{ID: uuid.New(), Username: username, DisplayName: displayName}, nil
}

func (s *handlerAuthRepoStub) RecordLogin(userID uuid.UUID) error { return nil }

func (s *handlerAuthRepoStub) UpdateCredentials(userID uuid.UUID, passwordHash, passwordAlgo string, passwordCost int, displayName string) error {
	return nil
}

func (s *handlerAuthRepoStub) FindByID(id uuid.UUID) (*model.User, error) {
	return &model.User{ID: id, Username: "alice", DisplayName: "Alice"}, nil
}

func (s *handlerAuthRepoStub) CreateSession(session *model.Session) error {
	s.session = session
	return nil
}

func (s *handlerAuthRepoStub) FindSessionByRefreshTokenSHA(sha string) (*model.Session, error) {
	if s.session == nil {
		return nil, repository.ErrNotFound
	}
	return s.session, nil
}

func (s *handlerAuthRepoStub) RevokeSession(id uuid.UUID) error { return nil }

func newHandlerUnderTest() *AuthHandler {
	repo := &handlerAuthRepoStub{}
	svc := service.NewAuthServiceWithDeps(&config.Config{
		AuthJWTSecret:      "secret",
		AuthRefreshHashKey: "hash-key",
		AuthAccessTokenTTL: time.Hour,
	}, repo, func(username, password string) string {
		return "Alice"
	})
	return &AuthHandler{authService: svc}
}

func TestLogin_ReturnsPythonStyleValidationError(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	h := newHandlerUnderTest()
	r.POST("/api/auth/token", h.Login)

	req := httptest.NewRequest(http.MethodPost, "/api/auth/token", bytes.NewBufferString(`{"username":""}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["error"] != "username and password are required" {
		t.Fatalf("unexpected error message: %v", body["error"])
	}
}

func TestMe_AlignsWithPythonResponseShape(t *testing.T) {
	gin.SetMode(gin.TestMode)

	h := &AuthHandler{}
	r := gin.New()
	r.GET("/api/auth/me", func(c *gin.Context) {
		c.Set("user_id", "u-1")
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

	if body["user_id"] != "u-1" {
		t.Fatalf("expected user_id=u-1, got %v", body["user_id"])
	}
	if body["display_name"] != "Alice" {
		t.Fatalf("expected display_name=Alice, got %v", body["display_name"])
	}
	if _, ok := body["id"]; ok {
		t.Fatalf("expected field id to be absent")
	}
	if _, ok := body["username"]; ok {
		t.Fatalf("expected field username to be absent")
	}
}

func TestLogout_ReturnsPythonStyleSuccessPayload(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	h := newHandlerUnderTest()
	r.POST("/api/auth/logout", h.Logout)

	req := httptest.NewRequest(http.MethodPost, "/api/auth/logout", bytes.NewBufferString(`{"refresh_token":"abc"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["message"] != "已登出" {
		t.Fatalf("unexpected message: %v", body["message"])
	}
}

func TestErrorMappings(t *testing.T) {
	if mapAuthError(service.ErrValidation) != http.StatusBadRequest {
		t.Fatalf("validation should map to 400")
	}
	if mapAuthError(service.ErrInvalidCredentials) != http.StatusUnauthorized {
		t.Fatalf("invalid credentials should map to 401")
	}
	if mapAuthError(service.ErrInvalidToken) != http.StatusUnauthorized {
		t.Fatalf("invalid token should map to 401")
	}
	if mapAuthError(errors.New("boom")) != http.StatusInternalServerError {
		t.Fatalf("unexpected errors should map to 500")
	}
}

func TestBuildAuthResponse_UserIDString(t *testing.T) {
	payload := buildAuthResponse(&service.LoginResult{
		AccessToken:  "a",
		RefreshToken: "r",
		TokenType:    "bearer",
		ExpiresIn:    123,
		User: &service.UserInfo{
			ID:          uuid.New().String(),
			Username:    "alice",
			DisplayName: "Alice",
			Roles:       []string{"admin"},
		},
	})
	if payload["token_type"] != "bearer" {
		t.Fatalf("expected token_type bearer")
	}
}
