package model

import (
	"time"

	"github.com/google/uuid"
)

type Session struct {
	ID              uuid.UUID `gorm:"type:uuid;primaryKey;default:gen_random_uuid()"`
	UserID          uuid.UUID `gorm:"type:uuid;index:idx_auth_sessions_user_id"`
	RefreshTokenSHA string    `gorm:"uniqueIndex;not null"`
	ExpiresAt       time.Time `gorm:"not null"`
	UserAgent       string
	IP              string
	RevokedAt       *time.Time
	CreatedAt       time.Time
}
