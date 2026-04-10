package model

import (
	"time"

	"github.com/google/uuid"
)

type Conversation struct {
	ID             uint32    `gorm:"primaryKey"`
	UserID         uuid.UUID `gorm:"type:uuid;not null;uniqueIndex:idx_conversations_user_conv"`
	ConversationID string    `gorm:"type:varchar(64);not null;uniqueIndex:idx_conversations_user_conv"`
	Title          string    `gorm:"type:varchar(256);default:'新会话'"`
	Messages       JSONArray `gorm:"type:jsonb;default:'[]'"`
	CreatedAt      time.Time
	UpdatedAt      time.Time
}
