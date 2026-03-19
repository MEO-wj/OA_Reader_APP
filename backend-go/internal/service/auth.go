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
	"github.com/oap/backend-go/internal/pkg/hash"
	"github.com/oap/backend-go/internal/pkg/jwt"
	"github.com/oap/backend-go/internal/repository"
)

var (
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrInvalidToken       = errors.New("invalid token")
)

type AuthService struct {
	userRepo       authRepository
	cfg            *config.Config
	campusVerifier func(username, password string) string
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
	if verifier == nil {
		verifier = campusVerify
	}
	return &AuthService{
		userRepo:       repo,
		cfg:            cfg,
		campusVerifier: verifier,
	}
}

func (s *AuthService) Login(username, password string) (*LoginResult, error) {
	username = strings.TrimSpace(username)
	if username == "" || password == "" {
		return nil, ErrInvalidCredentials
	}

	cred, err := s.userRepo.GetCredential(username)
	if err != nil {
		// 用户不存在，尝试校园 SSO 并自动创建
		if s.cfg.AuthAllowAutoUser && s.cfg.CampusAuthEnabled {
			displayName := s.campusVerifier(username, password)
			if displayName == "" {
				return nil, ErrInvalidCredentials
			}
			hashed, _ := hash.HashPassword(password, s.cfg.AuthPasswordCost)
			user, createErr := s.userRepo.CreateWithPassword(username, hashed, "bcrypt", s.cfg.AuthPasswordCost, displayName)
			if createErr != nil {
				return nil, ErrInvalidCredentials
			}
			cred, _ = s.userRepo.GetCredential(username)
			s.userRepo.RecordLogin(cred.UserID)
			return s.issueTokens(user)
		}
		return nil, ErrInvalidCredentials
	}

	// 本地密码验证
	if !hash.CheckPassword(password, cred.PasswordHash) {
		// 密码错误，尝试校园 SSO
		if s.cfg.CampusAuthEnabled {
			displayName := s.campusVerifier(username, password)
			if displayName != "" {
				// 校园 SSO 成功，更新密码
				hashed, _ := hash.HashPassword(password, s.cfg.AuthPasswordCost)
				s.userRepo.UpdateCredentials(cred.UserID, hashed, "bcrypt", s.cfg.AuthPasswordCost, displayName)
				cred, _ = s.userRepo.GetCredential(username)
			} else {
				return nil, ErrInvalidCredentials
			}
		} else {
			return nil, ErrInvalidCredentials
		}
	}

	s.userRepo.RecordLogin(cred.UserID)
	user, _ := s.userRepo.FindByID(cred.UserID)
	return s.issueTokens(user)
}

func campusVerify(username, password string) string {
	// TODO: 实现 CAS SSO 验证
	// 这里需要调用实际的校园 SSO 服务
	return ""
}

func (s *AuthService) issueTokens(user *model.User) (*LoginResult, error) {
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

	session := &model.Session{
		ID:              uuid.New(),
		UserID:          user.ID,
		RefreshTokenSHA: refreshSHA,
		ExpiresAt:       time.Now().Add(refreshTTL),
		CreatedAt:       time.Now(),
	}
	s.userRepo.CreateSession(session)

	accessToken, _ := jwt.GenerateToken(
		s.cfg.AuthJWTSecret,
		user.ID.String(),
		user.Username,
		user.DisplayName,
		user.Roles,
		int64(accessTTL.Seconds()),
	)

	return &LoginResult{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    "Bearer",
		ExpiresIn:    int(accessTTL.Seconds()),
		User: &UserInfo{
			ID:          user.ID.String(),
			Username:    user.Username,
			DisplayName: user.DisplayName,
			Roles:       user.Roles,
		},
	}, nil
}

func (s *AuthService) hashRefreshToken(token string) string {
	key := s.cfg.AuthRefreshHashKey
	data := key + token
	hash := sha256.Sum256([]byte(data))
	return base64.RawURLEncoding.EncodeToString(hash[:])
}

func (s *AuthService) Refresh(refreshToken string) (*LoginResult, error) {
	if refreshToken == "" {
		return nil, ErrInvalidToken
	}

	sha := s.hashRefreshToken(refreshToken)
	session, err := s.userRepo.FindSessionByRefreshTokenSHA(sha)
	if err != nil || session.RevokedAt != nil || session.ExpiresAt.Before(time.Now()) {
		return nil, ErrInvalidToken
	}

	s.userRepo.RevokeSession(session.ID)

	user, err := s.userRepo.FindByID(session.UserID)
	if err != nil || user == nil {
		return nil, ErrInvalidToken
	}
	return s.issueTokens(user)
}

func (s *AuthService) Logout(refreshToken string) error {
	if refreshToken == "" {
		return nil
	}
	sha := s.hashRefreshToken(refreshToken)
	session, err := s.userRepo.FindSessionByRefreshTokenSHA(sha)
	if err != nil {
		return nil
	}
	return s.userRepo.RevokeSession(session.ID)
}
