package model

import (
	"time"

	"github.com/google/uuid"
)

type User struct {
	ID               uuid.UUID  `gorm:"type:uuid;primaryKey;default:gen_random_uuid()"`
	Username         string     `gorm:"uniqueIndex;not null"`
	DisplayName      string     `gorm:"not null"`
	PasswordHash     string     `gorm:"not null"`
	PasswordAlgo     string     `gorm:"not null;default:bcrypt"`
	PasswordCost     int        `gorm:"not null;default:12"`
	Roles            StringArray `gorm:"type:text[];default:'{}'"`
	AvatarURL        string     `gorm:"default:null"`
	ProfileTags      StringArray `gorm:"type:text[];not null;default:'{}'"`
	Bio              string     `gorm:"not null;default:''"`
	ProfileUpdatedAt *time.Time
	IsVIP            bool       `gorm:"not null;default:false"`
	VIPExpiredAt     *time.Time
	CreatedAt        time.Time
	UpdatedAt        time.Time
	LastLoginAt      *time.Time
}
