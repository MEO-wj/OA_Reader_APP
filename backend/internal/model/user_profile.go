package model

import (
	"time"

	"github.com/google/uuid"
)

type UserProfile struct {
	ID            uint32    `gorm:"primaryKey"`
	UserID        uuid.UUID `gorm:"type:uuid;not null;uniqueIndex"`
	PortraitText  *string   `gorm:"type:text"`
	KnowledgeText *string   `gorm:"type:text"`
	Preferences   JSONMap   `gorm:"type:jsonb;default:'{}'"`
	CreatedAt     time.Time
	UpdatedAt     time.Time
}
