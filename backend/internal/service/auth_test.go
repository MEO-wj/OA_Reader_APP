package service

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/config"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/repository"
)

type fakeAuthRepo struct {
	credentialErr            error
	createWithPasswordCalled bool
	findByIDUser             *model.User
	findByIDErr              error
	lastCreatePasswordCost   int
}

func (f *fakeAuthRepo) GetCredential(username string) (*repository.UserCredential, error) {
	if f.credentialErr != nil {
		return nil, f.credentialErr
	}
	return &repository.UserCredential{UserID: uuid.New(), PasswordHash: "hash"}, nil
}

func (f *fakeAuthRepo) CreateWithPassword(username, passwordHash, passwordAlgo string, passwordCost int, displayName string) (*model.User, error) {
	f.createWithPasswordCalled = true
	f.lastCreatePasswordCost = passwordCost
	f.credentialErr = nil
	return &model.User{ID: uuid.New(), Username: username, DisplayName: displayName}, nil
}

func (f *fakeAuthRepo) RecordLogin(userID uuid.UUID) error { return nil }

func (f *fakeAuthRepo) UpdateCredentials(userID uuid.UUID, passwordHash, passwordAlgo string, passwordCost int, displayName string) error {
	return nil
}

func (f *fakeAuthRepo) FindByID(id uuid.UUID) (*model.User, error) {
	if f.findByIDErr != nil {
		return nil, f.findByIDErr
	}
	if f.findByIDUser != nil {
		return f.findByIDUser, nil
	}
	return &model.User{ID: id, Username: "u", DisplayName: "u"}, nil
}

func TestLogin_DoesNotAutoCreateUserWhenCampusVerifyFails(t *testing.T) {
	repo := &fakeAuthRepo{credentialErr: repository.ErrNotFound}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthAllowAutoUser:  true,
		CampusAuthEnabled:  true,
		AuthJWTSecret:      "secret",
		AuthAccessTokenTTL: time.Hour,
	}, repo, func(username, password string) string {
		return ""
	})

	_, err := svc.Login("new-user", "pwd", AuthMetadata{})
	if !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("expected ErrInvalidCredentials, got %v", err)
	}
	if repo.createWithPasswordCalled {
		t.Fatalf("expected no user creation when campus verify fails")
	}
}

func TestLogin_ReturnsInvalidCredentialsWhenCredentialLookupInternalError(t *testing.T) {
	repo := &fakeAuthRepo{credentialErr: errors.New("db unavailable")}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthAllowAutoUser:  true,
		CampusAuthEnabled:  true,
		AuthJWTSecret:      "secret",
		AuthAccessTokenTTL: time.Hour,
	}, repo, func(username, password string) string {
		t.Fatalf("campus verifier should not be called on internal errors")
		return ""
	})

	_, err := svc.Login("new-user", "pwd", AuthMetadata{})
	if !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("expected ErrInvalidCredentials, got %v", err)
	}
	if repo.createWithPasswordCalled {
		t.Fatalf("expected no user creation on internal repo errors")
	}
}

func TestLogin_UsesDefaultPasswordCostWhenConfigOutOfRange(t *testing.T) {
	repo := &fakeAuthRepo{credentialErr: repository.ErrNotFound}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthAllowAutoUser:  true,
		CampusAuthEnabled:  true,
		AuthPasswordCost:   2,
		AuthJWTSecret:      "secret",
		AuthAccessTokenTTL: time.Hour,
	}, repo, func(username, password string) string {
		return "Alice"
	})

	_, err := svc.Login("new-user", "pwd", AuthMetadata{})
	if err != nil {
		t.Fatalf("expected login success, got %v", err)
	}
	if repo.lastCreatePasswordCost != 12 {
		t.Fatalf("expected fallback cost 12, got %d", repo.lastCreatePasswordCost)
	}
}

func TestLogin_ReturnsJWTWith7DayTTL(t *testing.T) {
	repo := &fakeAuthRepo{}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthJWTSecret:     "secret",
		CampusAuthEnabled: true,
		// 不设置 AuthAccessTokenTTL，应使用默认 7 天
	}, repo, func(username, password string) string {
		return "TestUser"
	})

	result, err := svc.Login("u", "p", AuthMetadata{})
	if err != nil {
		t.Fatalf("login failed: %v", err)
	}

	if result.AccessToken == "" {
		t.Fatal("expected non-empty access_token")
	}
	if result.ExpiresIn != int(7*24*time.Hour.Seconds()) {
		t.Fatalf("expected expires_in=604800 (7 days), got %d", result.ExpiresIn)
	}
	if result.User == nil {
		t.Fatal("expected user info")
	}
}
