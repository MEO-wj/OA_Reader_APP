package repository

import (
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/model"
	"gorm.io/gorm"
)

var ErrNotFound = errors.New("not found")

type UserRepository struct {
	db *gorm.DB
}

type UserCredential struct {
	UserID       uuid.UUID
	PasswordHash string
	PasswordAlgo string
	PasswordCost int
}

type ProfileUpdateInput struct {
	DisplayName      string
	ProfileTags      []string
	Bio              string
	AvatarURL        string
	ProfileUpdatedAt time.Time
}

func NewUserRepository() *UserRepository {
	return &UserRepository{db: GetDB()}
}

func (r *UserRepository) FindByUsername(username string) (*model.User, error) {
	var user model.User
	if err := r.db.Where("username = ?", username).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
		return nil, err
	}
	return &user, nil
}

func (r *UserRepository) FindByID(id uuid.UUID) (*model.User, error) {
	var user model.User
	if err := r.db.First(&user, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
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

func (r *UserRepository) UpdateProfileByID(userID uuid.UUID, input ProfileUpdateInput) (*model.User, error) {
	updates := buildProfileUpdates(input)
	if err := r.db.Model(&model.User{}).Where("id = ?", userID).Updates(updates).Error; err != nil {
		return nil, err
	}
	return r.FindByID(userID)
}

func buildProfileUpdates(input ProfileUpdateInput) map[string]interface{} {
	return map[string]interface{}{
		"display_name":       input.DisplayName,
		"profile_tags":       model.StringArray(input.ProfileTags),
		"bio":                input.Bio,
		"avatar_url":         input.AvatarURL,
		"profile_updated_at": input.ProfileUpdatedAt,
	}
}

// GetCredential 获取用户凭证
func (r *UserRepository) GetCredential(username string) (*UserCredential, error) {
	var user model.User
	if err := r.db.Where("username = ?", username).First(&user).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
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
		Roles:        model.StringArray{},
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
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, ErrNotFound
		}
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
