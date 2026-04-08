# Backend Go 重构实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Python Flask 后端重构为 Go + Gin + GORM，保持 API 完全兼容

**Architecture:** Gin HTTP 框架 + GORM ORM + PostgreSQL/pgvector，AI 服务独立部署后端代理转发

**Tech Stack:** Go 1.21+, Gin, GORM, pgvector, JWT (HS256), bcrypt

---

## 实施顺序

### Task 1: 项目初始化

**Files:**
- Create: `backend-go/go.mod`
- Create: `backend-go/cmd/server/main.go`
- Create: `backend-go/.env.example`

**Step 1: 创建 go.mod**

```bash
mkdir -p backend-go/cmd/server
cd backend-go
go mod init github.com/oap/backend-go
```

**Step 2: 添加依赖**

```bash
go get github.com/gin-gonic/gin@v1.9.1
go get gorm.io/gorm@v1.25.5
go get gorm.io/driver/postgres@v1.5.4
go get github.com/golang-jwt/jwt/v5@v5.2.0
go get golang.org/x/crypto@v0.17.0
go get github.com/spf13/viper@v1.18.2
go get github.com/gin-contrib/cors@v1.5.0
go get github.com/google/uuid@v1.5.0
```

**Step 3: 创建 main.go 骨架**

```go
package main

import (
	"log"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()
	r.GET("/api/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})
	log.Println("Server starting on :4420")
	r.Run(":4420")
}
```

**Step 4: 创建 .env.example**

```
DATABASE_URL=postgres://user:password@localhost:5432/oap?sslmode=disable
AUTH_JWT_SECRET=your-jwt-secret-key
AUTH_REFRESH_HASH_KEY=your-refresh-hash-key
AUTH_ACCESS_TOKEN_TTL=168h
AUTH_REFRESH_TOKEN_TTL=168h
AUTH_PASSWORD_COST=12
AUTH_ALLOW_AUTO_USER_CREATION=true
CAMPUS_AUTH_ENABLED=true
CAMPUS_AUTH_URL=https://sso.example.edu.cn
CAMPUS_AUTH_TIMEOUT=10
CORS_ALLOW_ORIGINS=*
RATE_LIMIT_PER_DAY=1000
RATE_LIMIT_PER_HOUR=100
AI_END_URL=http://localhost:4421
```

**Step 5: 验证运行**

```bash
cd backend-go
go run cmd/server/main.go
# 访问 http://localhost:4420/api/health 应返回 {"status":"ok"}
```

---

### Task 2: 配置管理

**Files:**
- Create: `backend-go/internal/config/config.go`

**Step 1: 创建配置结构体**

```go
package config

import (
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	DatabaseURL           string
	AuthJWTSecret         string
	AuthRefreshHashKey    string
	AuthAccessTokenTTL    time.Duration
	AuthRefreshTokenTTL   time.Duration
	AuthPasswordCost      int
	AuthAllowAutoUser     bool
	CampusAuthEnabled     bool
	CampusAuthURL         string
	CampusAuthTimeout     int
	CORSAllowOrigins      []string
	RateLimitPerDay       int
	RateLimitPerHour      int
	AIEndURL              string
}

func Load(path string) (*Config, error) {
	viper.SetConfigFile(path)
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err != nil {
		return nil, err
	}

	var cfg Config
	if err := viper.Unmarshal(&cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 3: 数据库模型

**Files:**
- Create: `backend-go/internal/model/user.go`
- Create: `backend-go/internal/model/session.go`
- Create: `backend-go/internal/model/article.go`
- Create: `backend-go/internal/model/vector.go`

**Step 1: User 模型**

```go
package model

import (
	"time"

	"github.com/google/uuid"
)

type User struct {
	ID           uuid.UUID `gorm:"type:uuid;primaryKey;default:gen_random_uuid()"`
	Username     string    `gorm:"uniqueIndex;not null"`
	DisplayName  string    `gorm:"not null"`
	PasswordHash string    `gorm:"not null"`
	PasswordAlgo string    `gorm:"not null;default:bcrypt"`
	PasswordCost int       `gorm:"not null;default:12"`
	Roles        []string  `gorm:"type:text[];default:'{}'"`
	CreatedAt    time.Time
	UpdatedAt    time.Time
	LastLoginAt  *time.Time
}
```

**Step 2: Session 模型**

```go
package model

import (
	"time"

	"github.com/google/uuid"
)

type Session struct {
	ID              uuid.UUID `gorm:"type:uuid;primaryKey;default:gen_random_uuid()"`
	UserID          uuid.UUID `gorm:"type:uuid;index"`
	RefreshTokenSHA string    `gorm:"uniqueIndex;not null"`
	ExpiresAt       time.Time `gorm:"not null"`
	UserAgent       string
	IP              string
	RevokedAt       *time.Time
	CreatedAt       time.Time
}
```

**Step 3: Article 模型**

```go
package model

import (
	"time"
)

type Article struct {
	ID          uint64    `gorm:"primaryKey"`
	Title       string    `gorm:"not null"`
	Unit        string
	Link        string    `gorm:"uniqueIndex;not null"`
	PublishedOn time.Time `gorm:"index;not null"`
	Content     string    `gorm:"not null"`
	Summary     string    `gorm:"not null"`
	Attachments JSONArray `gorm:"type:jsonb;default:'[]'"`
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

type JSONArray []map[string]string
```

**Step 4: Vector 模型 (pgvector)**

```go
package model

import (
	"time"
)

// Vector 用于存储文章向量嵌入
type Vector struct {
	ID          uint64    `gorm:"primaryKey"`
	ArticleID   uint64    `gorm:"index"`
	Embedding   []float32 `gorm:"type:vector(1536)"`
	PublishedOn time.Time
	CreatedAt   time.Time
	UpdatedAt   time.Time
}
```

**Step 5: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 4: 数据库连接与迁移

**Files:**
- Create: `backend-go/internal/repository/db.go`

**Step 1: 创建数据库连接**

```go
package repository

import (
	"log"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"

	"github.com/oap/backend-go/internal/model"
)

var DB *gorm.DB

func InitDB(databaseURL string) error {
	var err error
	DB, err = gorm.Open(postgres.Open(databaseURL), &gorm.Config{})
	if err != nil {
		return err
	}

	// 自动迁移
	if err := DB.AutoMigrate(&model.User{}, &model.Session{}, &model.Article{}); err != nil {
		return err
	}

	// 创建 pgvector 扩展 (如需要)
	DB.Exec("CREATE EXTENSION IF NOT EXISTS vector")

	log.Println("Database initialized")
	return nil
}

func GetDB() *gorm.DB {
	return DB
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 5: JWT 工具

**Files:**
- Create: `backend-go/internal/pkg/jwt/jwt.go`

**Step 1: JWT 工具实现**

```go
package jwt

import (
	"github.com/golang-jwt/jwt/v5"
)

type Claims struct {
	jwt.RegisteredClaims
	Name  string   `json:"name,omitempty"`
	Roles []string `json:"roles,omitempty"`
}

func GenerateToken(secret string, userID string, name string, roles []string, ttl int64) (string, error) {
	claims := Claims{
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Duration(ttl) * time.Second)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
		Name:  name,
		Roles: roles,
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}

func ParseToken(tokenString string, secret string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		return []byte(secret), nil
	})
	if err != nil {
		return nil, err
	}

	if claims, ok := token.Claims.(*Claims); ok && token.Valid {
		return claims, nil
	}
	return nil, jwt.ErrSignatureInvalid
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 6: Hash 工具

**Files:**
- Create: `backend-go/internal/pkg/hash/bcrypt.go`

**Step 1: bcrypt 工具**

```go
package hash

import (
	"crypto/sha256"
	"encoding/hex"

	"golang.org/x/crypto/bcrypt"
)

func HashPassword(password string, cost int) (string, error) {
	bytes, err := bcrypt.GenerateFromPassword([]byte(password), cost)
	return string(bytes), err
}

func CheckPassword(password, hash string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(hash), []byte(password))
	return err == nil
}

func SHA256(data string) string {
	h := sha256.New()
	h.Write([]byte(data))
	return hex.EncodeToString(h.Sum(nil))
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 7: 用户 Repository

**Files:**
- Create: `backend-go/internal/repository/user.go`

**Step 1: 用户数据访问层**

```go
package repository

import (
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/model"
)

type UserRepository struct {
	db *gorm.DB
}

func NewUserRepository() *UserRepository {
	return &UserRepository{db: GetDB()}
}

func (r *UserRepository) FindByUsername(username string) (*model.User, error) {
	var user model.User
	if err := r.db.Where("username = ?", username).First(&user).Error; err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) FindByID(id uuid.UUID) (*model.User, error) {
	var user model.User
	if err := r.db.First(&user, "id = ?", id).Error; err != nil {
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) Create(user *model.User) error {
	return r.db.Create(user).Error
}

func (r *UserRepository) Update(user *model.User) error {
	return r.db.Save(user).Error
}
```

**Step 2: Session Repository**

```go
func (r *UserRepository) CreateSession(session *model.Session) error {
	return r.db.Create(session).Error
}

func (r *UserRepository) FindSessionByRefreshTokenSHA(sha string) (*model.Session, error) {
	var session model.Session
	if err := r.db.Where("refresh_token_sha = ?", sha).First(&session).Error; err != nil {
		return nil, err
	}
	return &session, nil
}

func (r *UserRepository) RevokeSession(id uuid.UUID) error {
	return r.db.Model(&model.Session{}).Where("id = ?", id).Update("revoked_at", time.Now()).Error
}

func (r *UserRepository) RevokeAllUserSessions(userID uuid.UUID) error {
	return r.db.Model(&model.Session{}).Where("user_id = ?", userID).Update("revoked_at", time.Now()).Error
}
```

**Step 3: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 8: 认证服务

**Files:**
- Create: `backend-go/internal/service/auth.go`

**Step 1: 认证服务实现**

```go
package service

import (
	"crypto/rand"
	"encoding/hex"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/pkg/hash"
	"github.com/oap/backend-go/internal/pkg/jwt"
	"github.com/oap/backend-go/internal/repository"
)

type AuthService struct {
	userRepo *repository.UserRepository
	cfg      *Config
}

type LoginResult struct {
	AccessToken  string
	RefreshToken string
	TokenType    string
	ExpiresIn    int
	User         *UserInfo
}

type UserInfo struct {
	ID          string   `json:"id"`
	Username    string   `json:"username"`
	DisplayName string   `json:"display_name"`
	Roles       []string `json:"roles"`
}

func NewAuthService(cfg *Config) *AuthService {
	return &AuthService{
		userRepo: repository.NewUserRepository(),
		cfg:      cfg,
	}
}

func (s *AuthService) Login(username, password string) (*LoginResult, error) {
	user, err := s.userRepo.FindByUsername(username)
	if err != nil {
		// 尝试校园 SSO
		return s.campusLogin(username, password)
	}

	// 本地验证
	if !hash.CheckPassword(password, user.PasswordHash) {
		// 尝试校园 SSO
		return s.campusLogin(username, password)
	}

	return s.issueTokens(user)
}

func (s *AuthService) campusLogin(username, password) (*LoginResult, error) {
	if !s.cfg.CampusAuthEnabled {
		return nil, ErrInvalidCredentials
	}

	// TODO: 实现 CAS SSO 登录
	return nil, ErrInvalidCredentials
}

func (s *AuthService) issueTokens(user *model.User) (*LoginResult, error) {
	// 生成 refresh token (48 bytes)
	refreshBytes := make([]byte, 48)
	rand.Read(refreshBytes)
	refreshToken := hex.EncodeToString(refreshBytes)
	refreshSHA := hash.SHA256(refreshToken)

	// 创建 session
	session := &model.Session{
		ID:              uuid.New(),
		UserID:          user.ID,
		RefreshTokenSHA: refreshSHA,
		ExpiresAt:       time.Now().Add(s.cfg.AuthRefreshTokenTTL),
		CreatedAt:       time.Now(),
	}
	s.userRepo.CreateSession(session)

	// 生成 access token
	accessToken, _ := jwt.GenerateToken(
		s.cfg.AuthJWTSecret,
		user.ID.String(),
		user.DisplayName,
		user.Roles,
		int(s.cfg.AuthAccessTokenTTL.Seconds()),
	)

	return &LoginResult{
		AccessToken:  accessToken,
		RefreshToken: refreshToken,
		TokenType:    "Bearer",
		ExpiresIn:    int(s.cfg.AuthAccessTokenTTL.Seconds()),
		User: &UserInfo{
			ID:          user.ID.String(),
			Username:    user.Username,
			DisplayName: user.DisplayName,
			Roles:       user.Roles,
		},
	}, nil
}

func (s *AuthService) Refresh(refreshToken string) (*LoginResult, error) {
	sha := hash.SHA256(refreshToken)
	session, err := s.userRepo.FindSessionByRefreshTokenSHA(sha)
	if err != nil || session.RevokedAt != nil || session.ExpiresAt.Before(time.Now()) {
		return nil, ErrInvalidToken
	}

	// 撤销旧 session
	s.userRepo.RevokeSession(session.ID)

	// 获取用户
	user, _ := s.userRepo.FindByID(session.UserID)
	return s.issueTokens(user)
}

func (s *AuthService) Logout(refreshToken string) error {
	sha := hash.SHA256(refreshToken)
	session, err := s.userRepo.FindSessionByRefreshTokenSHA(sha)
	if err != nil {
		return nil
	}
	return s.userRepo.RevokeSession(session.ID)
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 9: 认证中间件

**Files:**
- Create: `backend-go/internal/middleware/auth.go`

**Step 1: JWT 认证中间件**

```go
package middleware

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/oap/backend-go/internal/pkg/jwt"
)

func AuthRequired(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		auth := c.GetHeader("Authorization")
		if !strings.HasPrefix(auth, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing token"})
			return
		}

		token := strings.TrimPrefix(auth, "Bearer ")
		claims, err := jwt.ParseToken(token, jwtSecret)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}

		c.Set("user_id", claims.Subject)
		c.Set("user_name", claims.Name)
		c.Set("user_roles", claims.Roles)
		c.Next()
	}
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 10: 文章 Repository

**Files:**
- Create: `backend-go/internal/repository/article.go`

**Step 1: 文章数据访问层**

```go
package repository

import (
	"time"

	"github.com/oap/backend-go/internal/model"
)

type ArticleRepository struct {
	db *gorm.DB
}

func NewArticleRepository() *ArticleRepository {
	return &ArticleRepository{db: GetDB()}
}

func (r *ArticleRepository) FindToday() ([]model.Article, error) {
	var articles []model.Article
	today := time.Now().Truncate(24 * time.Hour)
	if err := r.db.Where("published_on >= ?", today).
		Order("published_on DESC, id DESC").
		Find(&articles).Error; err != nil {
		return nil, err
	}
	return articles, nil
}

func (r *ArticleRepository) FindPageV1(beforeID, limit int) ([]model.Article, error) {
	var articles []model.Article
	if err := r.db.Where("id < ?", beforeID).
		Order("id DESC").
		Limit(limit).
		Find(&articles).Error; err != nil {
		return nil, err
	}
	return articles, nil
}

func (r *ArticleRepository) FindPageV2(beforeDate string, beforeID, limit int) ([]model.Article, error) {
	var articles []model.Article
	date, _ := time.Parse("2006-01-02", beforeDate)
	if err := r.db.Where("(published_on, id) < (?, ?)", date, beforeID).
		Order("published_on DESC, id DESC").
		Limit(limit).
		Find(&articles).Error; err != nil {
		return nil, err
	}
	return articles, nil
}

func (r *ArticleRepository) Count() (int64, error) {
	var count int64
	if err := r.db.Model(&model.Article{}).Count(&count).Error; err != nil {
		return 0, err
	}
	return count, nil
}

func (r *ArticleRepository) FindByID(id uint64) (*model.Article, error) {
	var article model.Article
	if err := r.db.First(&article, id).Error; err != nil {
		return nil, err
	}
	return &article, nil
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 11: 文章服务

**Files:**
- Create: `backend-go/internal/service/articles.go`

**Step 1: 文章服务实现**

```go
package service

import (
	"time"

	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/repository"
)

type ArticleService struct {
	repo *repository.ArticleRepository
}

type PaginatedResponse struct {
	Articles       []ArticleDTO      `json:"articles"`
	HasMore        bool               `json:"has_more"`
	NextBeforeDate *string            `json:"next_before_date"`
	NextBeforeID   *int64             `json:"next_before_id"`
}

type ArticleDTO struct {
	ID          uint64  `json:"id"`
	Title       string  `json:"title"`
	Unit        string  `json:"unit,omitempty"`
	Link        string  `json:"link,omitempty"`
	PublishedOn string  `json:"published_on,omitempty"`
	Summary     string  `json:"summary,omitempty"`
	Attachments *[]map[string]string `json:"attachments,omitempty"`
}

func NewArticleService() *ArticleService {
	return &ArticleService{repo: repository.NewArticleRepository()}
}

func (s *ArticleService) GetToday() (*PaginatedResponse, error) {
	articles, err := s.repo.FindToday()
	if err != nil {
		return nil, err
	}
	return s.buildResponse(articles), nil
}

func (s *ArticleService) GetPage(v int, beforeDate string, beforeID, limit int) (*PaginatedResponse, error) {
	var articles []model.Article
	var err error

	if v == 2 {
		articles, err = s.repo.FindPageV2(beforeDate, beforeID, limit)
	} else {
		articles, err = s.repo.FindPageV1(beforeID, limit)
	}
	if err != nil {
		return nil, err
	}
	return s.buildResponse(articles), nil
}

func (s *ArticleService) GetCount() (int64, error) {
	return s.repo.Count()
}

func (s *ArticleService) GetByID(id uint64) (*model.Article, error) {
	return s.repo.FindByID(id)
}

func (s *ArticleService) buildResponse(articles []model.Article) *PaginatedResponse {
	hasMore := len(articles) > 0
	var nextDate *string
	var nextID *int64

	if hasMore && len(articles) > 0 {
		last := articles[len(articles)-1]
		dateStr := last.PublishedOn.Format("2006-01-02")
		nextDate = &dateStr
		nextID = &last.ID
	}

	dtos := make([]ArticleDTO, len(articles))
	for i, a := range articles {
		dtos[i] = ArticleDTO{
			ID:          a.ID,
			Title:       a.Title,
			Unit:        a.Unit,
			Link:        a.Link,
			PublishedOn: a.PublishedOn.Format("2006-01-02"),
			Summary:     a.Summary,
		}
	}

	return &PaginatedResponse{
		Articles:       dtos,
		HasMore:        hasMore,
		NextBeforeDate: nextDate,
		NextBeforeID:   nextID,
	}
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 12: ETag 中间件

**Files:**
- Create: `backend-go/internal/middleware/etag.go`

**Step 1: ETag 条件请求中间件**

```go
package middleware

import (
	"crypto/md5"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
)

func ETAG(c *gin.Context) {
	c.Next()

	// 跳过非 200 响应
	if c.Writer.Status() != 200 {
		return
	}

	// 获取响应 body
	body, ok := c.Get("response_body")
	if !ok {
		return
	}

	data, _ := json.Marshal(body)
	etag := fmt.Sprintf(`"%x"`, md5.Sum(data))
	c.Header("ETag", etag)
	c.Header("Cache-Control", "max-age=3600, public")

	if c.GetHeader("If-None-Match") == etag {
		c.AbortWithStatus(http.StatusNotModified)
	}
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 13: 认证 Handler

**Files:**
- Create: `backend-go/internal/handler/auth.go`

**Step 1: 认证 Handler**

```go
package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/oap/backend-go/internal/service"
)

type AuthHandler struct {
	authService *service.AuthService
}

func NewAuthHandler(authService *service.AuthService) *AuthHandler {
	return &AuthHandler{authService: authService}
}

type LoginRequest struct {
	Username string `json:"username" binding:"required"`
	Password string `json:"password" binding:"required"`
}

type RefreshRequest struct {
	RefreshToken string `json:"refresh_token" binding:"required"`
}

type LogoutRequest struct {
	RefreshToken string `json:"refresh_token" binding:"required"`
}

func (h *AuthHandler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}

	result, err := h.authService.Login(req.Username, req.Password)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid credentials"})
		return
	}

	c.JSON(http.StatusOK, result)
}

func (h *AuthHandler) Refresh(c *gin.Context) {
	var req RefreshRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}

	result, err := h.authService.Refresh(req.RefreshToken)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
		return
	}

	c.JSON(http.StatusOK, result)
}

func (h *AuthHandler) Logout(c *gin.Context) {
	var req LogoutRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid request"})
		return
	}

	h.authService.Logout(req.RefreshToken)
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *AuthHandler) Me(c *gin.Context) {
	userID, _ := c.Get("user_id")
	name, _ := c.Get("user_name")
	roles, _ := c.Get("user_roles")

	c.JSON(http.StatusOK, gin.H{
		"id":           userID,
		"username":     name,
		"display_name": name,
		"roles":        roles,
	})
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 14: 文章 Handler

**Files:**
- Create: `backend-go/internal/handler/articles.go`

**Step 1: 文章 Handler**

```go
package handler

import (
	"crypto/md5"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/oap/backend-go/internal/service"
)

type ArticleHandler struct {
	articleService *service.ArticleService
}

func NewArticleHandler(articleService *service.ArticleService) *ArticleHandler {
	return &ArticleHandler{articleService: articleService}
}

func (h *ArticleHandler) GetToday(c *gin.Context) {
	result, err := h.articleService.GetToday()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch articles"})
		return
	}
	h.sendWithETag(c, result)
}

func (h *ArticleHandler) GetPage(c *gin.Context) {
	v, _ := strconv.Atoi(c.DefaultQuery("v", "1"))
	beforeDate := c.Query("before_date")
	beforeID, _ := strconv.ParseInt(c.DefaultQuery("before_id", "0"), 10, 64)
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))

	result, err := h.articleService.GetPage(v, beforeDate, int(beforeID), limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch articles"})
		return
	}
	h.sendWithETag(c, result)
}

func (h *ArticleHandler) GetCount(c *gin.Context) {
	count, err := h.articleService.GetCount()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to count articles"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"total": count})
}

func (h *ArticleHandler) GetByID(c *gin.Context) {
	id, err := strconv.ParseUint(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid id"})
		return
	}

	article, err := h.articleService.GetByID(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "article not found"})
		return
	}

	c.JSON(http.StatusOK, article)
}

func (h *ArticleHandler) sendWithETag(c *gin.Context, data interface{}) {
	jsonBytes, _ := json.Marshal(data)
	etag := fmt.Sprintf(`"%x"`, md5.Sum(jsonBytes))

	if c.GetHeader("If-None-Match") == etag {
		c.AbortWithStatus(http.StatusNotModified)
		return
	}

	c.Header("ETag", etag)
	c.Header("Cache-Control", "max-age=3600, public")
	c.JSON(http.StatusOK, data)
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 15: AI 代理 Handler

**Files:**
- Create: `backend-go/internal/handler/ai.go`

**Step 1: AI 代理 Handler**

```go
package handler

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/gin-gonic/gin"
)

type AIHandler struct {
	aiEndURL string
}

func NewAIHandler(aiEndURL string) *AIHandler {
	return &AIHandler{aiEndURL: aiEndURL}
}

func (h *AIHandler) proxy(c *gin.Context, path string) {
	target, _ := url.Parse(h.aiEndURL)
	proxy := httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.URL.Path = path
		},
	}
	proxy.ServeHTTP(c.Writer, c.Request)
}

func (h *AIHandler) Ask(c *gin.Context) {
	h.proxy(c, "/ask")
}

func (h *AIHandler) ClearMemory(c *gin.Context) {
	h.proxy(c, "/clear_memory")
}

func (h *AIHandler) Embed(c *gin.Context) {
	h.proxy(c, "/embed")
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build ./...
```

---

### Task 16: 路由组装

**Files:**
- Modify: `backend-go/cmd/server/main.go`

**Step 1: 组装所有路由**

```go
package main

import (
	"log"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"

	"github.com/oap/backend-go/internal/config"
	"github.com/oap/backend-go/internal/handler"
	"github.com/oap/backend-go/internal/middleware"
	"github.com/oap/backend-go/internal/repository"
	"github.com/oap/backend-go/internal/service"
)

func main() {
	// 加载配置
	cfg, err := config.Load("backend-go/.env")
	if err != nil {
		log.Fatal("Failed to load config:", err)
	}

	// 初始化数据库
	if err := repository.InitDB(cfg.DatabaseURL); err != nil {
		log.Fatal("Failed to init db:", err)
	}

	// 初始化服务
	authService := service.NewAuthService(cfg)
	articleService := service.NewArticleService()

	// 初始化处理器
	authHandler := handler.NewAuthHandler(authService)
	articleHandler := handler.NewArticleHandler(articleService)
	aiHandler := handler.NewAIHandler(cfg.AIEndURL)

	// Gin 路由
	r := gin.Default()

	// CORS
	r.Use(cors.New(cors.Config{
		AllowOrigins:     cfg.CORSAllowOrigins,
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization"},
		ExposeHeaders:    []string{"Content-Length", "ETag"},
		AllowCredentials: true,
	}))

	// 健康检查
	r.GET("/api/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// 认证路由
	auth := r.Group("/api/auth")
	{
		auth.POST("/token", authHandler.Login)
		auth.POST("/token/refresh", authHandler.Refresh)
		auth.POST("/logout", authHandler.Logout)
		auth.GET("/me", middleware.AuthRequired(cfg.AuthJWTSecret), authHandler.Me)
	}

	// 文章路由
	articles := r.Group("/api/articles")
	{
		articles.GET("/today", articleHandler.GetToday)
		articles.GET("/", articleHandler.GetPage)
		articles.GET("/count", articleHandler.GetCount)
		articles.GET("/:id", articleHandler.GetByID)
	}

	// AI 路由 (需要认证)
	ai := r.Group("/api/ai")
	ai.Use(middleware.AuthRequired(cfg.AuthJWTSecret))
	{
		ai.POST("/ask", aiHandler.Ask)
		ai.POST("/clear_memory", aiHandler.ClearMemory)
		ai.POST("/embed", aiHandler.Embed)
	}

	log.Println("Server starting on :4420")
	r.Run(":4420")
}
```

**Step 2: 验证编译**

```bash
cd backend-go
go build -o server ./cmd/server
```

---

### Task 17: 集成测试

**Files:**
- Create: `backend-go/tests/api_test.go`

**Step 1: API 集成测试**

```go
package tests

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestHealthEndpoint(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/api/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	req, _ := http.NewRequest("GET", "/api/health", nil)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("Expected status 200, got %d", w.Code)
	}
}
```

**Step 2: 运行测试**

```bash
cd backend-go
go test ./...
```

---

## 执行选项

**Plan complete and saved to `docs/plans/2026-03-19-backend-go-refactor-implementation.md`**

**两个执行选项:**

**1. Subagent-Driven (当前 session)** - 我按任务逐个 dispatch subagent 实现，每个任务后 review，快速迭代

**2. Parallel Session (新 session)** - 在新 session 中使用 executing-plans skill，批量执行带检查点

你选择哪个方式？