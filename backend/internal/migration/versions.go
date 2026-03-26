package migration

import (
	"github.com/oap/backend-go/internal/model"
	"gorm.io/gorm"
)

func DefaultVersions(_ *gorm.DB) []Version {
	return []Version{
		{
			ID: "2026032601_base_schema",
			Up: func(tx *gorm.DB) error {
				return tx.AutoMigrate(&model.User{}, &model.Session{}, &model.Article{})
			},
		},
		{
			ID: "2026032602_user_profile_fields",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`
					ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url text;
					ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_tags text[] NOT NULL DEFAULT '{}';
					ALTER TABLE users ADD COLUMN IF NOT EXISTS bio text NOT NULL DEFAULT '';
					ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_updated_at timestamptz;
					ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip boolean NOT NULL DEFAULT false;
					ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expired_at timestamptz;
					UPDATE users SET bio = '' WHERE bio IS NULL;
					UPDATE users SET profile_tags = '{}' WHERE profile_tags IS NULL;
					UPDATE users SET is_vip = false WHERE is_vip IS NULL;
				`).Error
			},
		},
		{
			ID: "2026032603_article_created_at_index",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`
					CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles (created_at DESC);
				`).Error
			},
		},
	}
}

func Run(db *gorm.DB) error {
	return NewRunner(NewGormStore(db), DefaultVersions(db)).Run()
}
