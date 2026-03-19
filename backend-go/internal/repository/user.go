package repository

import (
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/model"
	"gorm.io/gorm"
)

type UserRepository struct {
	db *gorm.DB
}

type UserCredential struct {
	UserID       uuid.UUID
	PasswordHash string
	PasswordAlgo string
	PasswordCost int
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

// GetCredential 获取用户凭证
func (r *UserRepository) GetCredential(username string) (*UserCredential, error) {
	var user model.User
	if err := r.db.Where("username = ?", username).First(&user).Error; err != nil {
		return nil, err
	}
	return &UserCredential{
		UserID:       user.ID,
		PasswordHash: user.PasswordHash,
		PasswordAlgo: user.PasswordAlgo,
		PasswordCost: user.PasswordCost,
	}, nil
}

// CreateWithPassword 创建用户（带密码）
func (r *UserRepository) CreateWithPassword(username, passwordHash, passwordAlgo string, passwordCost int, displayName string) (*model.User, error) {
	user := &model.User{
		ID:           uuid.New(),
		Username:     username,
		DisplayName:  displayName,
		PasswordHash: passwordHash,
		PasswordAlgo: passwordAlgo,
		PasswordCost: passwordCost,
		Roles:        []string{},
	}
	if err := r.db.Create(user).Error; err != nil {
		return nil, err
	}
	return user, nil
}

// UpdateCredentials 更新用户凭证
func (r *UserRepository) UpdateCredentials(userID uuid.UUID, passwordHash, passwordAlgo string, passwordCost int, displayName string) error {
	updates := map[string]interface{}{
		"password_hash": passwordHash,
		"password_algo": passwordAlgo,
		"password_cost": passwordCost,
	}
	if displayName != "" {
		updates["display_name"] = displayName
	}
	return r.db.Model(&model.User{}).Where("id = ?", userID).Updates(updates).Error
}

// RecordLogin 记录登录时间
func (r *UserRepository) RecordLogin(userID uuid.UUID) error {
	now := time.Now()
	return r.db.Model(&model.User{}).Where("id = ?", userID).Update("last_login_at", now).Error
}

// CreateSession 创建会话
func (r *UserRepository) CreateSession(session *model.Session) error {
	return r.db.Create(session).Error
}

// FindSessionByRefreshTokenSHA 通过 refresh token SHA 查找会话
func (r *UserRepository) FindSessionByRefreshTokenSHA(sha string) (*model.Session, error) {
	var session model.Session
	if err := r.db.Where("refresh_token_sha = ?", sha).First(&session).Error; err != nil {
		return nil, err
	}
	return &session, nil
}

// RevokeSession 撤销会话
func (r *UserRepository) RevokeSession(id uuid.UUID) error {
	return r.db.Model(&model.Session{}).Where("id = ?", id).Update("revoked_at", time.Now()).Error
}

// RevokeAllUserSessions 撤销用户所有会话
func (r *UserRepository) RevokeAllUserSessions(userID uuid.UUID) error {
	return r.db.Model(&model.Session{}).Where("user_id = ?", userID).Update("revoked_at", time.Now()).Error
}
