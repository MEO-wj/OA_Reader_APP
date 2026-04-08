package migration

import (
	"fmt"

	"gorm.io/gorm"
)

type Version struct {
	ID string
	Up func(tx *gorm.DB) error
}

type Store interface {
	EnsureSchemaMigrationsTable() error
	HasVersion(version string) (bool, error)
	Apply(version string, up func(tx *gorm.DB) error) error
}

type Runner struct {
	store    Store
	versions []Version
}

func NewRunner(store Store, versions []Version) *Runner {
	return &Runner{
		store:    store,
		versions: versions,
	}
}

func (r *Runner) Run() error {
	if err := r.store.EnsureSchemaMigrationsTable(); err != nil {
		return fmt.Errorf("ensure schema_migrations: %w", err)
	}

	for _, version := range r.versions {
		applied, err := r.store.HasVersion(version.ID)
		if err != nil {
			return fmt.Errorf("check migration %s: %w", version.ID, err)
		}
		if applied {
			continue
		}
		if err := r.store.Apply(version.ID, version.Up); err != nil {
			return fmt.Errorf("apply migration %s: %w", version.ID, err)
		}
	}

	return nil
}

type GormStore struct {
	db *gorm.DB
}

func NewGormStore(db *gorm.DB) *GormStore {
	return &GormStore{db: db}
}

func (s *GormStore) EnsureSchemaMigrationsTable() error {
	return s.db.Exec(`
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`).Error
}

func (s *GormStore) HasVersion(version string) (bool, error) {
	var count int64
	if err := s.db.Raw(
		"SELECT COUNT(1) FROM schema_migrations WHERE version = ?",
		version,
	).Scan(&count).Error; err != nil {
		return false, err
	}
	return count > 0, nil
}

func (s *GormStore) Apply(version string, up func(tx *gorm.DB) error) error {
	return s.db.Transaction(func(tx *gorm.DB) error {
		if err := up(tx); err != nil {
			return err
		}
		return tx.Exec(
			"INSERT INTO schema_migrations (version) VALUES (?)",
			version,
		).Error
	})
}
