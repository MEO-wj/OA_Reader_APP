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

func TestConversationAndSessionUseDistinctCompositeUniqueIndexTags(t *testing.T) {
	conversationType := reflect.TypeOf(Conversation{})
	conversationUserID, _ := conversationType.FieldByName("UserID")
	conversationID, _ := conversationType.FieldByName("ConversationID")

	if !strings.Contains(conversationUserID.Tag.Get("gorm"), "uniqueIndex:idx_conversations_user_conv") {
		t.Fatalf("Conversation.UserID missing idx_conversations_user_conv")
	}
	if !strings.Contains(conversationID.Tag.Get("gorm"), "uniqueIndex:idx_conversations_user_conv") {
		t.Fatalf("Conversation.ConversationID missing idx_conversations_user_conv")
	}

	sessionType := reflect.TypeOf(ConversationSession{})
	sessionUserID, _ := sessionType.FieldByName("UserID")
	sessionConversationID, _ := sessionType.FieldByName("ConversationID")

	if !strings.Contains(sessionUserID.Tag.Get("gorm"), "uniqueIndex:idx_sessions_user_conv") {
		t.Fatalf("ConversationSession.UserID missing idx_sessions_user_conv")
	}
	if !strings.Contains(sessionConversationID.Tag.Get("gorm"), "uniqueIndex:idx_sessions_user_conv") {
		t.Fatalf("ConversationSession.ConversationID missing idx_sessions_user_conv")
	}
}

func TestArticlePublishedOnUsesDateTypeTag(t *testing.T) {
	field, ok := reflect.TypeOf(Article{}).FieldByName("PublishedOn")
	if !ok {
		t.Fatal("Article.PublishedOn not found")
	}
	tag := field.Tag.Get("gorm")
	if !strings.Contains(tag, "type:date") {
		t.Fatalf("expected type:date in tag, got %s", tag)
	}
}

func TestVectorPublishedOnUsesDateTypeAndNotNullTag(t *testing.T) {
	field, ok := reflect.TypeOf(Vector{}).FieldByName("PublishedOn")
	if !ok {
		t.Fatal("Vector.PublishedOn not found")
	}
	tag := field.Tag.Get("gorm")
	if !strings.Contains(tag, "type:date") || !strings.Contains(tag, "not null") {
		t.Fatalf("unexpected Vector.PublishedOn tag: %s", tag)
	}
}

func TestConversationLikeModelsUseUint32PrimaryKey(t *testing.T) {
	cases := []struct {
		name string
		typ  reflect.Type
	}{
		{name: "Conversation", typ: reflect.TypeOf(Conversation{})},
		{name: "ConversationSession", typ: reflect.TypeOf(ConversationSession{})},
		{name: "UserProfile", typ: reflect.TypeOf(UserProfile{})},
	}

	for _, tc := range cases {
		field, ok := tc.typ.FieldByName("ID")
		if !ok {
			t.Fatalf("%s.ID not found", tc.name)
		}
		if field.Type.Kind() != reflect.Uint32 {
			t.Fatalf("%s.ID expected uint32, got %s", tc.name, field.Type.Kind())
		}
	}
}
