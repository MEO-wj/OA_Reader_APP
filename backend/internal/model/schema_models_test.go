package model

import (
	"reflect"
	"strings"
	"testing"
)

func TestUserProfileUserIDUsesUUIDUniqueIndex(t *testing.T) {
	field, _ := reflect.TypeOf(UserProfile{}).FieldByName("UserID")
	tag := field.Tag.Get("gorm")
	if !strings.Contains(tag, "type:uuid") || !strings.Contains(tag, "uniqueIndex") {
		t.Fatalf("unexpected UserProfile.UserID tag: %s", tag)
	}
}

func TestSkillReferenceHasCompositeUniqueIndexTag(t *testing.T) {
	typ := reflect.TypeOf(SkillReference{})
	skillID, _ := typ.FieldByName("SkillID")
	filePath, _ := typ.FieldByName("FilePath")

	if !strings.Contains(skillID.Tag.Get("gorm"), "uniqueIndex:idx_skill_file") {
		t.Fatalf("SkillID missing composite unique index tag")
	}
	if !strings.Contains(filePath.Tag.Get("gorm"), "uniqueIndex:idx_skill_file") {
		t.Fatalf("FilePath missing composite unique index tag")
	}
}
