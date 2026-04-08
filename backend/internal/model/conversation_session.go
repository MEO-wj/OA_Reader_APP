package model

import (
	"time"

	"github.com/google/uuid"
)

type ConversationSession struct {
	ID             uint64    `gorm:"primaryKey"`
	UserID         uuid.UUID `gorm:"type:uuid;not null;uniqueIndex:idx_user_conv"`
	ConversationID string    `gorm:"type:varchar(64);not null;uniqueIndex:idx_user_conv"`
	Title          string    `gorm:"type:varchar(256);default:'新会话'"`
	CreatedAt      time.Time
	UpdatedAt      time.Time
}
