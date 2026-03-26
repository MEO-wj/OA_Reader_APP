package model

import (
	"reflect"
	"testing"
)

func TestUserModel_ContainsProfileFields(t *testing.T) {
	userType := reflect.TypeOf(User{})

	requiredFields := []string{
		"AvatarURL",
		"ProfileTags",
		"Bio",
		"ProfileUpdatedAt",
		"IsVIP",
		"VIPExpiredAt",
	}

	for _, fieldName := range requiredFields {
		if _, ok := userType.FieldByName(fieldName); !ok {
			t.Fatalf("expected User to contain field %s", fieldName)
		}
	}
}
