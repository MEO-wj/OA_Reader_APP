package repository

import (
	"log"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var DB *gorm.DB

func autoMigrateModels() []interface{} {
	return []interface{}{
		&model.User{},
		&model.Session{},
		&model.Article{},
		&model.Vector{},
		&model.Conversation{},
		&model.ConversationSession{},
		&model.UserProfile{},
		&model.Skill{},
		&model.SkillReference{},
	}
}

func InitDB(databaseURL string) error {
	var err error
	DB, err = gorm.Open(postgres.Open(databaseURL), &gorm.Config{})
	if err != nil {
		return err
	}

	// 自动迁移
	if err := DB.AutoMigrate(autoMigrateModels()...); err != nil {
		return err
	}

	// 创建 pgvector 扩展 (如需要)
	DB.Exec("CREATE EXTENSION IF NOT EXISTS vector")

	log.Println("Database initialized")
	return nil
}

func GetDB() *gorm.DB {
	return DB
}
