package model

import (
	"reflect"
	"sync"
	"testing"

	"gorm.io/gorm/schema"
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

func TestUserModel_VIPFieldsUseStableColumnNames(t *testing.T) {
	cache := &sync.Map{}
	userSchema, err := schema.Parse(&User{}, cache, schema.NamingStrategy{})
	if err != nil {
		t.Fatalf("parse user schema: %v", err)
	}

	isVIPField := userSchema.LookUpField("IsVIP")
	if isVIPField == nil {
		t.Fatal("expected IsVIP field in schema")
	}
	if got := isVIPField.DBName; got != "is_vip" {
		t.Fatalf("expected IsVIP column is_vip, got %s", got)
	}

	vipExpiredAtField := userSchema.LookUpField("VIPExpiredAt")
	if vipExpiredAtField == nil {
		t.Fatal("expected VIPExpiredAt field in schema")
	}
	if got := vipExpiredAtField.DBName; got != "vip_expired_at" {
		t.Fatalf("expected VIPExpiredAt column vip_expired_at, got %s", got)
	}
}
