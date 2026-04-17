package repository

import (
	"reflect"
	"testing"
)

func TestAutoMigrateModelsIncludesSchemaSyncModels(t *testing.T) {
	models := autoMigrateModels()

	got := map[string]bool{}
	for _, m := range models {
		got[reflect.TypeOf(m).Elem().Name()] = true
	}

	expected := []string{
		"User", "Article", "Vector",
		"Conversation", "ConversationSession", "UserProfile",
		"Skill", "SkillReference",
	}

	for _, name := range expected {
		if !got[name] {
			t.Fatalf("missing model in AutoMigrate list: %s", name)
		}
	}
}
