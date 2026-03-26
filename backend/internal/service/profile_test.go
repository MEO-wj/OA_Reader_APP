package service

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/repository"
)

type fakeProfileRepo struct {
	user          *model.User
	findErr       error
	updateErr     error
	lastUpdatedID uuid.UUID
	lastUpdated   ProfileUpdateInput
}

func (f *fakeProfileRepo) FindByID(id uuid.UUID) (*model.User, error) {
	if f.findErr != nil {
		return nil, f.findErr
	}
	if f.user != nil {
		return f.user, nil
	}
	return nil, repository.ErrNotFound
}

func (f *fakeProfileRepo) UpdateProfileByID(id uuid.UUID, input ProfileUpdateInput) (*model.User, error) {
	if f.updateErr != nil {
		return nil, f.updateErr
	}
	f.lastUpdatedID = id
	f.lastUpdated = input
	if f.user == nil {
		return nil, repository.ErrNotFound
	}

	next := *f.user
	next.DisplayName = input.DisplayName
	next.ProfileTags = input.ProfileTags
	next.Bio = input.Bio
	next.AvatarURL = input.AvatarURL
	next.ProfileUpdatedAt = &input.ProfileUpdatedAt
	f.user = &next
	return &next, nil
}

func TestProfileService_GetProfile_ReturnsMappedProfile(t *testing.T) {
	updatedAt := time.Date(2026, 3, 26, 12, 0, 0, 0, time.UTC)
	repo := &fakeProfileRepo{
		user: &model.User{
			ID:               uuid.New(),
			Username:         "20240001",
			DisplayName:      "张三",
			Roles:            []string{"student"},
			AvatarURL:        "https://example.com/a.jpg",
			ProfileTags:      []string{"计算机"},
			Bio:              "bio",
			ProfileUpdatedAt: &updatedAt,
			IsVIP:            true,
			VIPExpiredAt:     &updatedAt,
		},
	}

	svc := NewProfileService(repo)
	got, err := svc.GetProfile(repo.user.ID)
	if err != nil {
		t.Fatalf("GetProfile returned error: %v", err)
	}

	if got.DisplayName != "张三" {
		t.Fatalf("expected display_name 张三, got %s", got.DisplayName)
	}
	if got.AvatarURL != "https://example.com/a.jpg" {
		t.Fatalf("unexpected avatar_url: %s", got.AvatarURL)
	}
	if len(got.ProfileTags) != 1 || got.ProfileTags[0] != "计算机" {
		t.Fatalf("unexpected profile_tags: %#v", got.ProfileTags)
	}
	if !got.IsVIP {
		t.Fatal("expected is_vip true")
	}
}

func TestProfileService_UpdateProfile_ValidatesInput(t *testing.T) {
	repo := &fakeProfileRepo{
		user: &model.User{ID: uuid.New(), Username: "20240001", DisplayName: "张三"},
	}
	svc := NewProfileService(repo)

	_, err := svc.UpdateProfile(repo.user.ID, ProfileUpdateInput{
		DisplayName: "A",
	})
	if !errors.Is(err, ErrValidation) {
		t.Fatalf("expected ErrValidation for short display_name, got %v", err)
	}

	_, err = svc.UpdateProfile(repo.user.ID, ProfileUpdateInput{
		DisplayName: "张三",
		ProfileTags: []string{"1", "2", "3", "4", "5", "6"},
	})
	if !errors.Is(err, ErrValidation) {
		t.Fatalf("expected ErrValidation for too many tags, got %v", err)
	}

	_, err = svc.UpdateProfile(repo.user.ID, ProfileUpdateInput{
		DisplayName: "张三",
		Bio:         strings.Repeat("简", 81),
	})
	if !errors.Is(err, ErrValidation) {
		t.Fatalf("expected ErrValidation for bio too long, got %v", err)
	}
}

func TestProfileService_UpdateProfile_UsesCurrentTimeWhenMissingUpdatedAt(t *testing.T) {
	repo := &fakeProfileRepo{
		user: &model.User{ID: uuid.New(), Username: "20240001", DisplayName: "旧名字"},
	}
	svc := NewProfileService(repo)

	got, err := svc.UpdateProfile(repo.user.ID, ProfileUpdateInput{
		DisplayName: "新名字",
		ProfileTags: []string{"计算机", "效率控"},
		Bio:         "热爱校园自动化",
		AvatarURL:   "https://example.com/avatar.jpg",
	})
	if err != nil {
		t.Fatalf("UpdateProfile returned error: %v", err)
	}

	if repo.lastUpdatedID != repo.user.ID {
		t.Fatalf("expected update id %s, got %s", repo.user.ID, repo.lastUpdatedID)
	}
	if repo.lastUpdated.DisplayName != "新名字" {
		t.Fatalf("expected display_name to be forwarded")
	}
	if repo.lastUpdated.ProfileUpdatedAt.IsZero() {
		t.Fatal("expected profile_updated_at to be set")
	}
	if got.DisplayName != "新名字" {
		t.Fatalf("expected updated display_name, got %s", got.DisplayName)
	}
}
