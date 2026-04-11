package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/service"
)

type fakeProfileService struct {
	getProfileResponse    *service.UserProfile
	getProfileErr         error
	updateProfileResponse *service.UserProfile
	updateProfileErr      error
	lastGetID             uuid.UUID
	lastUpdateID          uuid.UUID
	lastUpdateInput       service.ProfileUpdateInput
}

func (f *fakeProfileService) GetProfile(userID uuid.UUID) (*service.UserProfile, error) {
	f.lastGetID = userID
	return f.getProfileResponse, f.getProfileErr
}

func (f *fakeProfileService) UpdateProfile(userID uuid.UUID, input service.ProfileUpdateInput) (*service.UserProfile, error) {
	f.lastUpdateID = userID
	f.lastUpdateInput = input
	return f.updateProfileResponse, f.updateProfileErr
}

func TestGetProfile_ReturnsProfileForUserIDInContext(t *testing.T) {
	gin.SetMode(gin.TestMode)

	userID := uuid.New()
	svc := &fakeProfileService{
		getProfileResponse: &service.UserProfile{
			ID:          userID.String(),
			Username:    "20240001",
			DisplayName: "张三",
		},
	}
	h := NewProfileHandler(svc, "")
	r := gin.New()
	r.GET("/api/user/profile", func(c *gin.Context) {
		c.Set("user_id", userID.String())
		h.GetProfile(c)
	})

	req := httptest.NewRequest(http.MethodGet, "/api/user/profile", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if svc.lastGetID != userID {
		t.Fatalf("expected service to receive %s, got %s", userID, svc.lastGetID)
	}
}

func TestGetProfile_ReturnsRelativeAvatarURLForUploadPath(t *testing.T) {
	gin.SetMode(gin.TestMode)

	userID := uuid.New()
	svc := &fakeProfileService{
		getProfileResponse: &service.UserProfile{
			ID:          userID.String(),
			Username:    "20240001",
			DisplayName: "张三",
			AvatarURL:   "/uploads/avatars/demo/avatar.png",
		},
	}
	h := NewProfileHandler(svc, "")
	r := gin.New()
	r.GET("/api/user/profile", func(c *gin.Context) {
		c.Set("user_id", userID.String())
		h.GetProfile(c)
	})

	req := httptest.NewRequest(http.MethodGet, "/api/user/profile", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["avatar_url"] != "/uploads/avatars/demo/avatar.png" {
		t.Fatalf("unexpected avatar_url: %v", body["avatar_url"])
	}
}

func TestUpdateProfile_RejectsInvalidPayload(t *testing.T) {
	gin.SetMode(gin.TestMode)

	h := NewProfileHandler(&fakeProfileService{}, "")
	r := gin.New()
	r.PATCH("/api/user/profile", func(c *gin.Context) {
		c.Set("user_id", uuid.New().String())
		h.UpdateProfile(c)
	})

	req := httptest.NewRequest(http.MethodPatch, "/api/user/profile", bytes.NewBufferString(`{"profile_updated_at":"bad-time"}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestUpdateProfile_ReturnsUpdatedProfile(t *testing.T) {
	gin.SetMode(gin.TestMode)

	userID := uuid.New()
	updatedAt := time.Date(2026, 3, 26, 12, 0, 0, 0, time.UTC)
	svc := &fakeProfileService{
		updateProfileResponse: &service.UserProfile{
			ID:               userID.String(),
			Username:         "20240001",
			DisplayName:      "张三",
			ProfileTags:      []string{"计算机"},
			Bio:              "热爱校园自动化",
			AvatarURL:        "https://example.com/a.jpg",
			ProfileUpdatedAt: &updatedAt,
		},
	}
	h := NewProfileHandler(svc, "")
	r := gin.New()
	r.PATCH("/api/user/profile", func(c *gin.Context) {
		c.Set("user_id", userID.String())
		h.UpdateProfile(c)
	})

	req := httptest.NewRequest(http.MethodPatch, "/api/user/profile", bytes.NewBufferString(`{
		"display_name":"张三",
		"profile_tags":["计算机"],
		"bio":"热爱校园自动化",
		"avatar_url":"https://example.com/a.jpg",
		"profile_updated_at":"2026-03-26T12:00:00Z"
	}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	if svc.lastUpdateID != userID {
		t.Fatalf("expected update user %s, got %s", userID, svc.lastUpdateID)
	}
	if svc.lastUpdateInput.DisplayName != "张三" {
		t.Fatalf("expected display_name forwarded, got %s", svc.lastUpdateInput.DisplayName)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if body["display_name"] != "张三" {
		t.Fatalf("expected display_name in response, got %v", body["display_name"])
	}
}
