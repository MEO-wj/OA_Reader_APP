package repository

import (
	"reflect"
	"testing"
	"time"

	"github.com/oap/backend-go/internal/model"
)

func TestBuildProfileUpdates_UsesStringArrayForProfileTags(t *testing.T) {
	updatedAt := time.Date(2026, 3, 26, 14, 52, 32, 0, time.UTC)

	updates := buildProfileUpdates(ProfileUpdateInput{
		DisplayName:      "黄应辉",
		ProfileTags:      []string{},
		Bio:              "",
		AvatarURL:        "http://localhost:4420/uploads/avatar.webp",
		ProfileUpdatedAt: updatedAt,
	})

	got, ok := updates["profile_tags"].(model.StringArray)
	if !ok {
		t.Fatalf("expected profile_tags to use model.StringArray, got %T", updates["profile_tags"])
	}
	if !reflect.DeepEqual(got, model.StringArray{}) {
		t.Fatalf("expected empty StringArray, got %#v", got)
	}
}
