package model

import (
	"time"
)

// Vector 用于存储文章向量嵌入
type Vector struct {
	ID          uint64    `gorm:"primaryKey"`
	ArticleID   uint64    `gorm:"index"`
	Embedding   []float32 `gorm:"type:vector(1024)"`
	PublishedOn time.Time `gorm:"type:date;not null"`
	CreatedAt   time.Time
	UpdatedAt   time.Time
}
