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
				return tx.AutoMigrate(&model.User{}, &model.Article{})
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
		{
			ID: "2026040701_conversation_indexes",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`
					CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_user_conv ON conversations (user_id, conversation_id);
					CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_user_conv ON conversation_sessions (user_id, conversation_id);
					DO $$
					BEGIN
						IF EXISTS (
							SELECT 1 FROM pg_indexes
							WHERE schemaname = 'public'
							  AND indexname = 'idx_user_conv'
						) THEN
							DROP INDEX IF EXISTS idx_user_conv;
						END IF;
					END $$;
				`).Error
			},
		},
		{
			ID: "2026040702_ai_end_baseline_indexes_extensions",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`
					CREATE EXTENSION IF NOT EXISTS vector;
					CREATE EXTENSION IF NOT EXISTS pg_trgm;

					CREATE INDEX IF NOT EXISTS idx_articles_published_on ON articles (published_on);
					CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops);
					CREATE INDEX IF NOT EXISTS idx_articles_content_trgm ON articles USING gin (content gin_trgm_ops);

					CREATE INDEX IF NOT EXISTS idx_vectors_published_on ON vectors (published_on);
					CREATE UNIQUE INDEX IF NOT EXISTS idx_vectors_article ON vectors(article_id);
					CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw ON vectors USING hnsw (embedding vector_cosine_ops);

					CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);
					CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON conversation_sessions(user_id);
					CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);
				`).Error
			},
		},
		{
			ID: "2026040703_sessions_user_index_conflict_fix",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`
					DO $$
					BEGIN
						IF EXISTS (
							SELECT 1 FROM pg_indexes
							WHERE schemaname = 'public'
							  AND tablename = 'sessions'
							  AND indexname = 'idx_sessions_user_id'
						) THEN
							IF EXISTS (
								SELECT 1 FROM pg_indexes
								WHERE schemaname = 'public'
								  AND indexname = 'idx_auth_sessions_user_id'
							) THEN
								DROP INDEX IF EXISTS idx_sessions_user_id;
							ELSE
								ALTER INDEX idx_sessions_user_id RENAME TO idx_auth_sessions_user_id;
							END IF;
						END IF;
					END $$;

					CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON conversation_sessions(user_id);
				`).Error
			},
		},
		{
			ID: "2026041001_shared_table_fk_constraints",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`
					DO $$ BEGIN
						ALTER TABLE vectors
						  ADD CONSTRAINT fk_vectors_article
						  FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE;
					EXCEPTION WHEN duplicate_object THEN NULL;
					END $$;

					DO $$ BEGIN
						ALTER TABLE skill_references
						  ADD CONSTRAINT fk_skill_references_skill
						  FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE;
					EXCEPTION WHEN duplicate_object THEN NULL;
					END $$;

					DROP INDEX IF EXISTS idx_vectors_article_id;
				`).Error
			},
		},
		{
			ID: "2026041501_cleanup_sessions",
			Up: func(tx *gorm.DB) error {
				return tx.Exec(`DROP TABLE IF EXISTS sessions`).Error
			},
		},
	}
}

func Run(db *gorm.DB) error {
	return NewRunner(NewGormStore(db), DefaultVersions(db)).Run()
}
