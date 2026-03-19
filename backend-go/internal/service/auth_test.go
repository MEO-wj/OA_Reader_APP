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
	createSessionCalled      bool
	findByIDUser             *model.User
	findByIDErr              error
	refreshSession           *model.Session
	findSessionErr           error
	revokeSessionCalled      bool
}

func (f *fakeAuthRepo) GetCredential(username string) (*repository.UserCredential, error) {
	if f.credentialErr != nil {
		return nil, f.credentialErr
	}
	return &repository.UserCredential{UserID: uuid.New(), PasswordHash: "hash"}, nil
}

func (f *fakeAuthRepo) CreateWithPassword(username, passwordHash, passwordAlgo string, passwordCost int, displayName string) (*model.User, error) {
	f.createWithPasswordCalled = true
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

func (f *fakeAuthRepo) CreateSession(session *model.Session) error {
	f.createSessionCalled = true
	return nil
}

func (f *fakeAuthRepo) FindSessionByRefreshTokenSHA(sha string) (*model.Session, error) {
	if f.findSessionErr != nil {
		return nil, f.findSessionErr
	}
	if f.refreshSession == nil {
		return nil, errors.New("not implemented")
	}
	return f.refreshSession, nil
}

func (f *fakeAuthRepo) RevokeSession(id uuid.UUID) error {
	f.revokeSessionCalled = true
	return nil
}

func TestLogin_DoesNotAutoCreateUserWhenCampusVerifyFails(t *testing.T) {
	repo := &fakeAuthRepo{credentialErr: errors.New("not found")}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthAllowAutoUser:  true,
		CampusAuthEnabled:  true,
		AuthJWTSecret:      "secret",
		AuthRefreshHashKey: "hash-key",
		AuthAccessTokenTTL: time.Hour,
	}, repo, func(username, password string) string {
		return ""
	})

	_, err := svc.Login("new-user", "pwd")
	if !errors.Is(err, ErrInvalidCredentials) {
		t.Fatalf("expected ErrInvalidCredentials, got %v", err)
	}
	if repo.createWithPasswordCalled {
		t.Fatalf("expected no user creation when campus verify fails")
	}
	if repo.createSessionCalled {
		t.Fatalf("expected no session creation when campus verify fails")
	}
}

func TestRefresh_ReturnsInvalidTokenWhenSessionUserNotFound(t *testing.T) {
	sessionUserID := uuid.New()
	repo := &fakeAuthRepo{
		refreshSession: &model.Session{
			ID:        uuid.New(),
			UserID:    sessionUserID,
			ExpiresAt: time.Now().Add(time.Hour),
		},
		findByIDErr: errors.New("user not found"),
	}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthJWTSecret:      "secret",
		AuthRefreshHashKey: "hash-key",
		AuthAccessTokenTTL: time.Hour,
	}, repo, nil)

	_, err := svc.Refresh("refresh-token")
	if !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("expected ErrInvalidToken, got %v", err)
	}
	if !repo.revokeSessionCalled {
		t.Fatalf("expected session to be revoked before issuing new tokens")
	}
}
