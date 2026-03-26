package service

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/config"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/pkg/alog"
	"github.com/oap/backend-go/internal/pkg/hash"
	"github.com/oap/backend-go/internal/pkg/jwt"
	"github.com/oap/backend-go/internal/repository"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrInvalidToken       = errors.New("invalid token")
	ErrValidation         = errors.New("validation error")
)

type AuthService struct {
	userRepo       authRepository
	cfg            *config.Config
	campusVerifier func(username, password string) string
}

type validationError struct {
	message string
}

func (e validationError) Error() string {
	return e.message
}

func (e validationError) Is(target error) bool {
	return target == ErrValidation
}

type AuthMetadata struct {
	RequestID string
	UserAgent string
	IP        string
}

type authRepository interface {
	GetCredential(username string) (*repository.UserCredential, error)
	CreateWithPassword(username, passwordHash, passwordAlgo string, passwordCost int, displayName string) (*model.User, error)
	RecordLogin(userID uuid.UUID) error
	UpdateCredentials(userID uuid.UUID, passwordHash, passwordAlgo string, passwordCost int, displayName string) error
	FindByID(id uuid.UUID) (*model.User, error)
	CreateSession(session *model.Session) error
	FindSessionByRefreshTokenSHA(sha string) (*model.Session, error)
	RevokeSession(id uuid.UUID) error
}

type LoginResult struct {
	AccessToken  string    `json:"access_token"`
	RefreshToken string    `json:"refresh_token"`
	TokenType    string    `json:"token_type"`
	ExpiresIn    int       `json:"expires_in"`
	User         *UserInfo `json:"user"`
}

type UserInfo struct {
	ID          string   `json:"id"`
	Username    string   `json:"username"`
	DisplayName string   `json:"display_name"`
	Roles       []string `json:"roles"`
}

func NewAuthService(cfg *config.Config) *AuthService {
	return NewAuthServiceWithDeps(cfg, repository.NewUserRepository(), nil)
}

func NewAuthServiceWithDeps(cfg *config.Config, repo authRepository, verifier func(username, password string) string) *AuthService {
	if cfg == nil {
		panic("config is required")
	}
	if strings.TrimSpace(cfg.AuthJWTSecret) == "" {
		panic("AUTH_JWT_SECRET 未配置")
	}
	if strings.TrimSpace(cfg.AuthRefreshHashKey) == "" {
		panic("AUTH_REFRESH_HASH_KEY 未配置")
	}
	if verifier == nil {
		verifier = campusVerify
	}
	return &AuthService{
		userRepo:       repo,
		cfg:            cfg,
		campusVerifier: verifier,
	}
}

func (s *AuthService) Login(username, password string, meta AuthMetadata) (*LoginResult, error) {
	username = strings.TrimSpace(username)
	alog.Authf("[AUTH][%s][service.login] begin username=%q", meta.RequestID, username)
	if username == "" || password == "" {
		alog.Authf("[AUTH][%s][service.login] validation failed: missing username/password", meta.RequestID)
		return nil, validationError{message: "username and password are required"}
	}

	cred, err := s.userRepo.GetCredential(username)
	if err != nil {
		if !errors.Is(err, repository.ErrNotFound) {
			alog.Authf("[AUTH][%s][service.login] credential lookup internal error: %v", meta.RequestID, err)
			return nil, ErrInvalidCredentials
		}
		alog.Authf("[AUTH][%s][service.login] user not found, try campus flow", meta.RequestID)
		if !s.cfg.AuthAllowAutoUser || !s.cfg.CampusAuthEnabled {
			alog.Authf("[AUTH][%s][service.login] auto user creation disabled", meta.RequestID)
			return nil, ErrInvalidCredentials
		}
		displayName := s.campusVerifier(username, password)
		if displayName == "" {
			alog.Authf("[AUTH][%s][service.login] campus verify failed on create path", meta.RequestID)
			return nil, ErrInvalidCredentials
		}
		alog.Authf("[AUTH][%s][service.login] campus verify success, creating user display_name=%q", meta.RequestID, displayName)
		hashed, hashErr := hash.HashPassword(password, s.passwordCost())
		if hashErr != nil {
			alog.Authf("[AUTH][%s][service.login] hash password failed on create path: %v", meta.RequestID, hashErr)
			return nil, ErrInvalidCredentials
		}
		user, createErr := s.userRepo.CreateWithPassword(username, hashed, "bcrypt", s.passwordCost(), displayName)
		if createErr != nil {
			alog.Authf("[AUTH][%s][service.login] create user failed: %v", meta.RequestID, createErr)
			return nil, ErrInvalidCredentials
		}
		alog.Authf("[AUTH][%s][service.login] user created user_id=%s", meta.RequestID, user.ID.String())
		cred, err = s.userRepo.GetCredential(username)
		if err != nil {
			alog.Authf("[AUTH][%s][service.login] get credential after create failed: %v", meta.RequestID, err)
			return nil, ErrInvalidCredentials
		}
		if recordErr := s.userRepo.RecordLogin(cred.UserID); recordErr != nil {
			alog.Authf("record login failed for %s: %v", cred.UserID.String(), recordErr)
		}
		return s.issueTokens(user, meta)
	}

	// 本地密码验证
	if !hash.CheckPassword(password, cred.PasswordHash) {
		alog.Authf("[AUTH][%s][service.login] local password mismatch, try campus flow", meta.RequestID)
		// 密码错误，尝试校园 SSO
		if s.cfg.CampusAuthEnabled {
			displayName := s.campusVerifier(username, password)
			if displayName != "" {
				alog.Authf("[AUTH][%s][service.login] campus verify success on update path display_name=%q", meta.RequestID, displayName)
				// 校园 SSO 成功，更新密码
				hashed, hashErr := hash.HashPassword(password, s.passwordCost())
				if hashErr != nil {
					alog.Authf("[AUTH][%s][service.login] hash password failed on update path: %v", meta.RequestID, hashErr)
					return nil, ErrInvalidCredentials
				}
				if updateErr := s.userRepo.UpdateCredentials(cred.UserID, hashed, "bcrypt", s.passwordCost(), displayName); updateErr != nil {
					alog.Authf("[AUTH][%s][service.login] update credentials failed: %v", meta.RequestID, updateErr)
					return nil, updateErr
				}
				cred, err = s.userRepo.GetCredential(username)
				if err != nil {
					alog.Authf("[AUTH][%s][service.login] get credential after update failed: %v", meta.RequestID, err)
					return nil, ErrInvalidCredentials
				}
			} else {
				alog.Authf("[AUTH][%s][service.login] campus verify failed on update path", meta.RequestID)
				return nil, ErrInvalidCredentials
			}
		} else {
			alog.Authf("[AUTH][%s][service.login] campus auth disabled and local password mismatch", meta.RequestID)
			return nil, ErrInvalidCredentials
		}
	}

	if recordErr := s.userRepo.RecordLogin(cred.UserID); recordErr != nil {
		alog.Authf("record login failed for %s: %v", cred.UserID.String(), recordErr)
	}
	user, err := s.userRepo.FindByID(cred.UserID)
	if err != nil {
		alog.Authf("[AUTH][%s][service.login] find user by id failed: %v", meta.RequestID, err)
		return nil, err
	}
	alog.Authf("[AUTH][%s][service.login] issuing tokens user_id=%s", meta.RequestID, user.ID.String())
	return s.issueTokens(user, meta)
}

func campusVerify(username, password string) string {
	// 调用校园 CAS SSO 验证
	displayName, err := casLoginAndGetName(username, password)
	if err != nil {
		alog.Authf("[CAS] verify failed for %s: %v", username, err)
		return ""
	}
	if displayName == "" {
		alog.Authf("[CAS] verify returned empty name for %s", username)
		return ""
	}
	alog.Authf("[CAS] verify success for %s: %s", username, displayName)
	return displayName
}

func (s *AuthService) issueTokens(user *model.User, meta AuthMetadata) (*LoginResult, error) {
	alog.Authf("[AUTH][%s][service.issue_tokens] begin user_id=%s", meta.RequestID, user.ID.String())
	// 生成 refresh token (48 bytes, base64 url-safe)
	refreshBytes := make([]byte, 48)
	rand.Read(refreshBytes)
	refreshToken := base64.RawURLEncoding.EncodeToString(refreshBytes)
	refreshSHA := s.hashRefreshToken(refreshToken)

	// 计算默认 TTL
	accessTTL := s.cfg.AuthAccessTokenTTL
	if accessTTL == 0 {
		accessTTL = time.Hour
	}
	refreshTTL := s.cfg.AuthRefreshTokenTTL
	if refreshTTL == 0 {
		refreshTTL = 7 * 24 * time.Hour
	}

	now := time.Now()
	session := &model.Session{
		ID:              uuid.New(),
		UserID:          user.ID,
		RefreshTokenSHA: refreshSHA,
		ExpiresAt:       now.Add(refreshTTL),
		UserAgent:       meta.UserAgent,
		IP:              meta.IP,
		CreatedAt:       now,
	}
	s.userRepo.CreateSession(session)
	alog.Authf("[AUTH][%s][service.issue_tokens] session created session_id=%s expire_at=%s", meta.RequestID, session.ID.String(), session.ExpiresAt.Format(time.RFC3339))

	accessToken, _ := jwt.GenerateToken(
		s.cfg.AuthJWTSecret,
		user.ID.String(),
		user.Username,
		user.DisplayName,
			[]string(user.Roles),
		int64(accessTTL.Seconds()),
	)

	return &LoginResult{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    "bearer",
		ExpiresIn:    int(accessTTL.Seconds()),
		User: &UserInfo{
			ID:          user.ID.String(),
			Username:    user.Username,
			DisplayName: user.DisplayName,
				Roles:       append([]string{}, []string(user.Roles)...),
			},
		}, nil
	}

func (s *AuthService) hashRefreshToken(token string) string {
	key := s.cfg.AuthRefreshHashKey
	data := key + token
	hash := sha256.Sum256([]byte(data))
	return base64.RawURLEncoding.EncodeToString(hash[:])
}

func (s *AuthService) Refresh(refreshToken string, meta AuthMetadata) (*LoginResult, error) {
	token := strings.TrimSpace(refreshToken)
	alog.Authf("[AUTH][%s][service.refresh] begin token_len=%d", meta.RequestID, len(token))
	if token == "" {
		alog.Authf("[AUTH][%s][service.refresh] validation failed: missing token", meta.RequestID)
		return nil, validationError{message: "refresh token missing"}
	}

	sha := s.hashRefreshToken(token)
	session, err := s.userRepo.FindSessionByRefreshTokenSHA(sha)
	if err != nil || session.RevokedAt != nil || session.ExpiresAt.Before(time.Now()) {
		alog.Authf("[AUTH][%s][service.refresh] invalid session err=%v revoked=%t expired=%t", meta.RequestID, err, session != nil && session.RevokedAt != nil, session != nil && session.ExpiresAt.Before(time.Now()))
		return nil, ErrInvalidToken
	}

	if err := s.userRepo.RevokeSession(session.ID); err != nil {
		alog.Authf("[AUTH][%s][service.refresh] revoke old session failed: %v", meta.RequestID, err)
		return nil, err
	}
	alog.Authf("[AUTH][%s][service.refresh] old session revoked session_id=%s", meta.RequestID, session.ID.String())

	user, err := s.userRepo.FindByID(session.UserID)
	if errors.Is(err, repository.ErrNotFound) || user == nil {
		alog.Authf("[AUTH][%s][service.refresh] user missing for session user_id=%s", meta.RequestID, session.UserID.String())
		return nil, ErrInvalidToken
	}
	if err != nil {
		alog.Authf("[AUTH][%s][service.refresh] find user failed: %v", meta.RequestID, err)
		return nil, err
	}
	alog.Authf("[AUTH][%s][service.refresh] issuing new tokens user_id=%s", meta.RequestID, user.ID.String())
	return s.issueTokens(user, meta)
}

func (s *AuthService) Logout(refreshToken string) error {
	token := strings.TrimSpace(refreshToken)
	alog.Authf("[AUTH][service.logout] begin token_len=%d", len(token))
	if token == "" {
		alog.Authf("[AUTH][service.logout] validation failed: missing token")
		return validationError{message: "refresh token missing"}
	}
	sha := s.hashRefreshToken(token)
	session, err := s.userRepo.FindSessionByRefreshTokenSHA(sha)
	if errors.Is(err, repository.ErrNotFound) {
		alog.Authf("[AUTH][service.logout] session not found, treat as success")
		return nil
	}
	if err != nil {
		alog.Authf("[AUTH][service.logout] find session failed: %v", err)
		return err
	}
	alog.Authf("[AUTH][service.logout] revoke session session_id=%s", session.ID.String())
	return s.userRepo.RevokeSession(session.ID)
}

func (s *AuthService) passwordCost() int {
	if s.cfg.AuthPasswordCost >= 4 && s.cfg.AuthPasswordCost <= 31 {
		return s.cfg.AuthPasswordCost
	}
	return 12
}
