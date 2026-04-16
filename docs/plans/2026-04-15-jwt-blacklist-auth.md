# 纯 JWT 认证重构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用纯 JWT 替换现有的 session rotation 机制，消除 sessions 表无限增长问题。

**Architecture:** 登录时签发长效 JWT（7 天），存在客户端 localStorage。服务端无状态 — 每次请求只解析 JWT 检查签名和过期时间，不查数据库。登出是纯前端行为（清 localStorage）。不再有 refresh token、不再有 session 写入、不再有黑名单。

**Tech Stack:** Go (golang-jwt/v5), React Native / Expo, TypeScript

**Breaking Change:** 是。需要前后端同步部署。

---

## 改动概览

### 后端（Go）

| 文件 | 操作 | 说明 |
|------|------|------|
| `internal/service/auth.go` | 修改 | 去掉 session/refresh/blacklist 逻辑 |
| `internal/handler/auth.go` | 修改 | 去掉 Refresh handler，Logout 改为空壳 |
| `internal/config/config.go` | 修改 | 去掉 refresh 相关配置 |
| `cmd/server/main.go` | 修改 | 去掉 refresh 路由 |
| `internal/model/session.go` | 保留 | 不删，停止写入即可 |
| 所有 `*_test.go` | 修改 | 更新测试 |

### 前端（TypeScript）

| 文件 | 操作 | 说明 |
|------|------|------|
| `services/auth.ts` | 删除 | 整个文件不再需要 |
| `storage/auth-storage.ts` | 修改 | 去掉 refresh_token 相关 |
| `services/profile-request.ts` | 删除 | 不再需要 |
| `services/profile.ts` | 修改 | 直接 fetch，去掉 wrapper |
| `app/_layout.tsx` | 修改 | 去掉 refresh 触发 |
| `app/_layout.web.tsx` | 修改 | 去掉 refresh 触发 |
| `app/login.tsx` | 修改 | 去掉 refresh_token 存储 |

---

## Task 1: 简化 AuthService — 去掉 session/refresh

**Files:**
- Modify: `backend/internal/service/auth.go`

**Step 1: 写失败测试**

更新 `backend/internal/service/auth_test.go`，先确保现有 session 相关测试会被移除：

```go
// 确认 authRepository 接口不再有 session 方法
// 确认 Login 不再创建 session
// 确认 Refresh 方法被移除
// 确认 Logout 方法被移除或改为 no-op
```

具体测试：

```go
// backend/internal/service/auth_test.go

package service

import (
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/config"
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
		AuthAllowAutoUser: true,
		CampusAuthEnabled: true,
		AuthJWTSecret:     "secret",
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
		AuthAllowAutoUser: true,
		CampusAuthEnabled: true,
		AuthJWTSecret:     "secret",
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
		AuthJWTSecret: "secret",
		// 不设置 AuthAccessTokenTTL，应使用默认 7 天
	}, repo, nil)

	result, err := svc.Login("u", "p", AuthMetadata{})
	if err != nil {
		t.Fatalf("login failed: %v", err)
	}

	if result.AccessToken == "" {
		t.Fatal("expected non-empty access_token")
	}
	if result.RefreshToken != "" {
		t.Fatal("expected empty refresh_token")
	}
	if result.ExpiresIn != int(7*24*time.Hour.Seconds()) {
		t.Fatalf("expected expires_in=604800 (7 days), got %d", result.ExpiresIn)
	}
	if result.User == nil {
		t.Fatal("expected user info")
	}
}

func TestLogin_ReturnsCustomTTL(t *testing.T) {
	repo := &fakeAuthRepo{}
	svc := NewAuthServiceWithDeps(&config.Config{
		AuthJWTSecret:      "secret",
		AuthAccessTokenTTL: 24 * time.Hour,
	}, repo, nil)

	result, err := svc.Login("u", "p", AuthMetadata{})
	if err != nil {
		t.Fatalf("login failed: %v", err)
	}
	if result.ExpiresIn != int(24*time.Hour.Seconds()) {
		t.Fatalf("expected expires_in=86400, got %d", result.ExpiresIn)
	}
}
```

**Step 2: 运行测试确认失败**

Run: `cd backend && go test ./internal/service/ -v`
Expected: FAIL — 旧测试引用了已删除的 session 方法

**Step 3: 实现**

重写 `backend/internal/service/auth.go`：

```go
package service

import (
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/config"
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
}

type LoginResult struct {
	AccessToken string    `json:"access_token"`
	TokenType   string    `json:"token_type"`
	ExpiresIn   int       `json:"expires_in"`
	User        *UserInfo `json:"user"`
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
		if s.cfg.CampusAuthEnabled {
			displayName := s.campusVerifier(username, password)
			if displayName != "" {
				alog.Authf("[AUTH][%s][service.login] campus verify success on update path display_name=%q", meta.RequestID, displayName)
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
	alog.Authf("[AUTH][%s][service.login] issuing token user_id=%s", meta.RequestID, user.ID.String())
	return s.issueTokens(user, meta)
}

func campusVerify(username, password string) string {
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

	accessTTL := s.cfg.AuthAccessTokenTTL
	if accessTTL == 0 {
		accessTTL = 7 * 24 * time.Hour
	}

	accessToken, err := jwt.GenerateToken(
		s.cfg.AuthJWTSecret,
		user.ID.String(),
		user.Username,
		user.DisplayName,
		[]string(user.Roles),
		int64(accessTTL.Seconds()),
	)
	if err != nil {
		alog.Authf("[AUTH][%s][service.issue_tokens] generate token failed: %v", meta.RequestID, err)
		return nil, err
	}

	return &LoginResult{
		AccessToken: accessToken,
		TokenType:   "bearer",
		ExpiresIn:   int(accessTTL.Seconds()),
		User: &UserInfo{
			ID:          user.ID.String(),
			Username:    user.Username,
			DisplayName: user.DisplayName,
			Roles:       append([]string{}, []string(user.Roles)...),
		},
	}, nil
}

func (s *AuthService) passwordCost() int {
	if s.cfg.AuthPasswordCost >= 4 && s.cfg.AuthPasswordCost <= 31 {
		return s.cfg.AuthPasswordCost
	}
	return 12
}
```

**变更摘要**：
- 移除 `LoginResult.RefreshToken` 字段
- 移除 `authRepository` 中的 `CreateSession`、`FindSessionByRefreshTokenSHA`、`RevokeSession`
- 移除 `Refresh()` 方法
- 移除 `Logout()` 方法（登出是纯前端行为）
- 移除 `hashRefreshToken()` 方法
- `issueTokens()` 不再创建 session，只生成 JWT
- 默认 TTL 从 1 小时改为 7 天
- 移除 `AuthRefreshHashKey` 校验
- 移除 `crypto/rand`、`encoding/base64`、`crypto/sha256`、`model` import

**Step 4: 运行测试确认通过**

Run: `cd backend && go test ./internal/service/ -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add internal/service/auth.go internal/service/auth_test.go
git commit -m "refactor(auth): remove session rotation, use pure JWT (7-day TTL)"
```

---

## Task 2: 更新 handler 层 — 去掉 Refresh 和 Logout

**Files:**
- Modify: `backend/internal/handler/auth.go`
- Modify: `backend/internal/handler/auth_test.go`

**Step 1: 写失败测试**

```go
// 在 auth_test.go 中添加：
func TestLogin_ResponseHasNoRefreshToken(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &handlerAuthRepoStub{}
	svc := service.NewAuthServiceWithDeps(&config.Config{
		AuthJWTSecret:      "secret",
		AuthAccessTokenTTL: time.Hour,
	}, repo, func(username, password string) string {
		return "Alice"
	})
	h := NewAuthHandler(svc)
	r := gin.New()
	r.POST("/api/auth/token", h.Login)

	req := httptest.NewRequest(http.MethodPost, "/api/auth/token", bytes.NewBufferString(`{"username":"alice","password":"pass"}`))
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
	if _, ok := body["refresh_token"]; ok {
		t.Fatalf("expected no refresh_token field, got %v", body["refresh_token"])
	}
	if body["access_token"] == nil || body["access_token"] == "" {
		t.Fatalf("expected non-empty access_token")
	}
}
```

**Step 2: 运行测试确认失败**

Run: `cd backend && go test ./internal/handler/ -run TestLogin_ResponseHasNoRefreshToken -v`
Expected: FAIL

**Step 3: 实现**

修改 `backend/internal/handler/auth.go`：

1. 删除 `RefreshRequest`、`LogoutRequest` struct
2. 删除 `Refresh()` 方法
3. 删除 `Logout()` 方法
4. 修改 `buildAuthResponse` 不返回 `refresh_token`：

```go
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
```

更新 `handlerAuthRepoStub`，移除 session 相关方法。

**Step 4: 运行测试确认通过**

Run: `cd backend && go test ./internal/handler/ -v`
Expected: PASS

**Step 5: Commit**

```bash
cd backend
git add internal/handler/auth.go internal/handler/auth_test.go
git commit -m "refactor(auth): remove Refresh and Logout handlers"
```

---

## Task 3: 更新路由和配置

**Files:**
- Modify: `backend/cmd/server/main.go`
- Modify: `backend/internal/config/config.go`

**Step 1: 修改 main.go**

移除 refresh 和 logout 路由：

```go
// 认证路由
auth := r.Group("/api/auth")
{
	auth.POST("/token", authHandler.Login)
	auth.GET("/me", middleware.AuthRequired(cfg.AuthJWTSecret), authHandler.Me)
}
```

**Step 2: 修改 config.go**

移除字段：
- `AuthRefreshHashKey string` + 对应 `mapstructure`
- `AuthRefreshTokenTTL time.Duration` + 对应 `mapstructure`

移除 `Load()` 中的 `BindEnv("AUTH_REFRESH_HASH_KEY")` 和 `BindEnv("AUTH_REFRESH_TOKEN_TTL")`。

**Step 3: 运行编译确认无错**

Run: `cd backend && go build ./...`
Expected: 无错误

**Step 4: Commit**

```bash
cd backend
git add cmd/server/main.go internal/config/config.go
git commit -m "refactor(auth): remove refresh route and refresh config fields"
```

---

## Task 4: 运行全部后端测试

**Step 1: 运行全部测试**

Run: `cd backend && go test ./... -v`
Expected: 全部 PASS

**Step 2: 修复任何失败的测试**

如果 `config_test.go` 或其他测试引用了已移除的配置字段，一并修复。

**Step 3: Commit**

```bash
cd backend
git add -A
git commit -m "test(auth): fix remaining test references"
```

---

## Task 5: 前端 — 去掉 refresh token 存储

**Files:**
- Modify: `OAP-app/storage/auth-storage.ts`

**Step 1: 移除 refresh token 相关代码**

从 `auth-storage.ts` 中移除：
- `REFRESH_TOKEN_KEY` 常量（line 11）
- `getRefreshToken` 函数（lines 86-88）
- `setRefreshToken` 函数（lines 90-96）
- `clearAuthStorage` 中对 `REFRESH_TOKEN_KEY` 的 removeItem 调用（line 147）

**Step 2: Commit**

```bash
cd OAP-app
git add storage/auth-storage.ts
git commit -m "refactor(auth): remove refresh token storage"
```

---

## Task 6: 前端 — 删除 auth.ts 和 profile-request.ts

**Files:**
- Delete: `OAP-app/services/auth.ts`
- Delete: `OAP-app/services/profile-request.ts`

**Step 1: 删除文件**

```bash
cd OAP-app
git rm services/auth.ts services/profile-request.ts
```

**Step 2: Commit**

```bash
git commit -m "refactor(auth): remove auth.ts and profile-request.ts"
```

---

## Task 7: 前端 — 简化 profile.ts

**Files:**
- Modify: `OAP-app/services/profile.ts`

**Step 1: 移除 refresh wrapper，直接调用 fetch**

```typescript
// OAP-app/services/profile.ts
import { Platform } from 'react-native';

import { buildAuthHeaders, getApiBaseUrl } from '@/services/api';
import { toStoredAvatarUrl } from '@/services/profile-avatar-url';
import { getAccessToken, setUserProfileRaw } from '@/storage/auth-storage';
import type { UserProfile } from '@/types/profile';
import { buildAvatarFormValue } from '@/services/profile-avatar-upload';

export type ProfileUpdatePayload = Pick<
  UserProfile,
  'display_name' | 'profile_tags' | 'bio' | 'profile_updated_at' | 'avatar_url'
>;

export type ProfileAvatarUploadPayload = {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  webFile?: File | null;
};

export type ProfileAvatarUploadResponse = {
  avatar_url: string;
};

export const PROFILE_API = {
  getProfile: '/user/profile',
  updateProfile: '/user/profile',
  uploadAvatar: '/user/profile/avatar',
} as const;

async function buildAuthorizedHeaders(includeJsonContentType = false) {
  const token = await getAccessToken();
  return {
    ...(includeJsonContentType ? { 'Content-Type': 'application/json' } : {}),
    ...buildAuthHeaders(token),
  };
}

async function parseErrorMessage(response: Response) {
  try {
    const data = await response.json();
    if (typeof data?.error === 'string' && data.error) {
      return data.error;
    }
  } catch {
    // ignore and fall through to generic status error
  }

  return `Profile API request failed with status ${response.status}`;
}

export async function fetchProfile() {
  const response = await fetch(`${getApiBaseUrl()}${PROFILE_API.getProfile}`, {
    headers: await buildAuthorizedHeaders(),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as UserProfile;
}

async function patchProfile(payload: ProfileUpdatePayload) {
  const response = await fetch(`${getApiBaseUrl()}${PROFILE_API.updateProfile}`, {
    method: 'PATCH',
    headers: await buildAuthorizedHeaders(true),
    body: JSON.stringify({
      ...payload,
      avatar_url: toStoredAvatarUrl(payload.avatar_url),
    }),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as UserProfile;
}

async function postProfileAvatar(payload: ProfileAvatarUploadPayload) {
  const formData = new FormData();
  formData.append('avatar', buildAvatarFormValue(payload, Platform.OS === 'web') as any);

  const response = await fetch(`${getApiBaseUrl()}${PROFILE_API.uploadAvatar}`, {
    method: 'POST',
    headers: await buildAuthorizedHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  const result = (await response.json()) as ProfileAvatarUploadResponse;
  return {
    ...result,
    avatar_url: toStoredAvatarUrl(result.avatar_url),
  };
}

export async function refreshProfileCache() {
  const profile = await fetchProfile();
  await setUserProfileRaw(JSON.stringify(profile));
  return profile;
}

export async function updateProfile(payload: ProfileUpdatePayload) {
  const profile = await patchProfile(payload);
  await setUserProfileRaw(JSON.stringify(profile));
  return profile;
}

export async function uploadProfileAvatar(payload: ProfileAvatarUploadPayload) {
  return await postProfileAvatar(payload);
}
```

**Step 2: Commit**

```bash
cd OAP-app
git add services/profile.ts
git commit -m "refactor(auth): remove session refresh retry from profile API"
```

---

## Task 8: 前端 — 去掉 layout 中的 refresh 触发

**Files:**
- Modify: `OAP-app/app/_layout.tsx`
- Modify: `OAP-app/app/_layout.web.tsx`

**Step 1: 修改 _layout.tsx**

移除：
- `import { refreshSessionOnForeground } from '@/services/auth';`（line 11）
- 整个 refresh 相关的 useEffect（lines 23-39）

**Step 2: 修改 _layout.web.tsx**

移除：
- `import { refreshSessionOnForeground } from '@/services/auth';`（line 15）
- 整个 refresh 相关的 useEffect（lines 134-158）

**Step 3: Commit**

```bash
cd OAP-app
git add app/_layout.tsx app/_layout.web.tsx
git commit -m "refactor(auth): remove refresh triggers from layouts"
```

---

## Task 9: 前端 — 简化登录流程

**Files:**
- Modify: `OAP-app/app/login.tsx`

**Step 1: 修改 login.tsx**

1. 从 import 中移除 `setRefreshToken`
2. 移除 `await setRefreshToken(data.refresh_token || null);`（line 57）

**Step 2: 搜索残留引用**

Run: `cd OAP-app && grep -rn "refreshSessionOnForeground\|setRefreshToken\|getRefreshToken\|refresh_token\|requestWithSessionRefresh" --include="*.ts" --include="*.tsx" .`
Expected: 无结果

**Step 3: Commit**

```bash
cd OAP-app
git add app/login.tsx
git commit -m "refactor(auth): remove refresh_token from login flow"
```

---

## Task 10: 数据库迁移 — 清理历史 sessions（可选）

**Files:**
- Modify: `backend/internal/migration/versions.go`

**Step 1: 添加 migration**

```go
{
    ID: "2026041501_cleanup_sessions",
    Up: func(tx *gorm.DB) error {
        return tx.Exec(`DELETE FROM sessions`).Error
    },
},
```

**Step 2: Commit**

```bash
cd backend
git add internal/migration/versions.go
git commit -m "migration: cleanup historical sessions"
```

---

## 对比：改动前后

| | 改之前 | 改之后 |
|---|---|---|
| 登录后 DB 写入 | 1 行 session + 1 行 user update | 0 |
| 切标签页请求 | 1 次 POST /refresh → 2 次 DB 操作 | 0 |
| access token 有效期 | 1 小时 | 7 天 |
| 每天新增 session 行 | ~1440 | 0 |
| sessions 表增长 | 无限增长 | 停止 |
| 后端代码 | ~329 行 auth.go | ~250 行（-24%） |
| 前端代码 | auth.ts + profile-request.ts + refresh 逻辑 | 全部删除 |
| 登出 | 服务端 revoke session | 客户端清 localStorage |
| 部署顺序 | - | 后端先（兼容旧前端返回 null refresh_token），再前端 |
