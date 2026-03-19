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
