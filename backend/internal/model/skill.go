package model

import "time"

type Skill struct {
	ID                uint32  `gorm:"primaryKey"`
	Name              string  `gorm:"type:varchar(100);not null;uniqueIndex"`
	Description       *string `gorm:"type:text"`
	VerificationToken *string `gorm:"type:varchar(100)"`
	Metadata          JSONMap `gorm:"type:jsonb;not null;default:'{}'"`
	Content           string  `gorm:"type:text;not null"`
	Tools             *string `gorm:"type:text"`
	IsStatic          bool    `gorm:"default:true"`
	CreatedAt         time.Time
	UpdatedAt         time.Time
}
