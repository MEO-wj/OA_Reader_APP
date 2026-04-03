package model

import "time"

type SkillReference struct {
	ID        uint32    `gorm:"primaryKey"`
	SkillID   uint32    `gorm:"not null;index;uniqueIndex:idx_skill_file"`
	FilePath  string    `gorm:"type:varchar(500);not null;uniqueIndex:idx_skill_file"`
	Content   string    `gorm:"type:text;not null"`
	CreatedAt time.Time
}
