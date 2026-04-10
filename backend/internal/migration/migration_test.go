package migration

import (
	"errors"
	"slices"
	"testing"

	"gorm.io/gorm"
)

type fakeStore struct {
	applied map[string]bool
	order   []string
	failOn  string
}

func newFakeStore() *fakeStore {
	return &fakeStore{applied: map[string]bool{}}
}

func (f *fakeStore) EnsureSchemaMigrationsTable() error {
	return nil
}

func (f *fakeStore) HasVersion(version string) (bool, error) {
	return f.applied[version], nil
}

func (f *fakeStore) Apply(version string, up func(tx *gorm.DB) error) error {
	if f.failOn == version {
		return errors.New("boom")
	}
	if err := up(nil); err != nil {
		return err
	}
	f.applied[version] = true
	f.order = append(f.order, version)
	return nil
}

func TestRunnerRun_AppliesPendingVersionsOnce(t *testing.T) {
	store := newFakeStore()
	runner := NewRunner(store, []Version{
		{
			ID: "2026032601",
			Up: func(tx *gorm.DB) error { return nil },
		},
		{
			ID: "2026032602",
			Up: func(tx *gorm.DB) error { return nil },
		},
	})

	if err := runner.Run(); err != nil {
		t.Fatalf("first run: %v", err)
	}
	if err := runner.Run(); err != nil {
		t.Fatalf("second run: %v", err)
	}

	if len(store.order) != 2 {
		t.Fatalf("expected 2 applied versions, got %d", len(store.order))
	}
	if store.order[0] != "2026032601" || store.order[1] != "2026032602" {
		t.Fatalf("unexpected apply order: %#v", store.order)
	}
}

func TestRunnerRun_StopsWhenVersionFails(t *testing.T) {
	store := newFakeStore()
	store.failOn = "2026032602"
	runner := NewRunner(store, []Version{
		{
			ID: "2026032601",
			Up: func(tx *gorm.DB) error { return nil },
		},
		{
			ID: "2026032602",
			Up: func(tx *gorm.DB) error { return nil },
		},
		{
			ID: "2026032603",
			Up: func(tx *gorm.DB) error { return nil },
		},
	})

	err := runner.Run()
	if err == nil {
		t.Fatal("expected error when version apply fails")
	}
	if !store.applied["2026032601"] {
		t.Fatal("expected first version to be applied")
	}
	if store.applied["2026032602"] {
		t.Fatal("expected failed version not to be recorded")
	}
	if store.applied["2026032603"] {
		t.Fatal("expected versions after failure not to be applied")
	}
}

func TestRunnerRun_PassesTransactionToVersion(t *testing.T) {
	store := newFakeStore()
	var received *gorm.DB

	runner := NewRunner(store, []Version{
		{
			ID: "2026032601",
			Up: func(tx *gorm.DB) error {
				received = tx
				return nil
			},
		},
	})

	if err := runner.Run(); err != nil {
		t.Fatalf("Run: %v", err)
	}
	if received != nil {
		t.Fatalf("expected fake store to pass nil tx in test double, got %#v", received)
	}
}

func TestDefaultVersions_ContainsConversationIndexFixMigration(t *testing.T) {
	versions := DefaultVersions(nil)
	ids := make([]string, 0, len(versions))
	for _, v := range versions {
		ids = append(ids, v.ID)
	}

	if !slices.Contains(ids, "2026040701_conversation_indexes") {
		t.Fatalf("missing migration 2026040701_conversation_indexes, got: %#v", ids)
	}
}

func TestDefaultVersions_ContainsAiEndBaselineIndexAndExtensionMigration(t *testing.T) {
	versions := DefaultVersions(nil)
	ids := make([]string, 0, len(versions))
	for _, v := range versions {
		ids = append(ids, v.ID)
	}

	if !slices.Contains(ids, "2026040702_ai_end_baseline_indexes_extensions") {
		t.Fatalf("missing migration 2026040702_ai_end_baseline_indexes_extensions, got: %#v", ids)
	}
}

func TestDefaultVersions_ContainsSessionsUserIndexConflictFixMigration(t *testing.T) {
	versions := DefaultVersions(nil)
	ids := make([]string, 0, len(versions))
	for _, v := range versions {
		ids = append(ids, v.ID)
	}

	if !slices.Contains(ids, "2026040703_sessions_user_index_conflict_fix") {
		t.Fatalf("missing migration 2026040703_sessions_user_index_conflict_fix, got: %#v", ids)
	}
}

func TestDefaultVersions_ContainsSharedTableFkConstraintsMigration(t *testing.T) {
	versions := DefaultVersions(nil)
	ids := make([]string, 0, len(versions))
	for _, v := range versions {
		ids = append(ids, v.ID)
	}

	if !slices.Contains(ids, "2026041001_shared_table_fk_constraints") {
		t.Fatalf("missing migration 2026041001_shared_table_fk_constraints, got: %#v", ids)
	}
}
