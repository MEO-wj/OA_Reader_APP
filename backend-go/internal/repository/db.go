package repository

import (
	"log"

	"gorm.io/driver/postgres"
	"gorm.io/gorm"

	"github.com/oap/backend-go/internal/model"
)

var DB *gorm.DB

func InitDB(databaseURL string) error {
	var err error
	DB, err = gorm.Open(postgres.Open(databaseURL), &gorm.Config{})
	if err != nil {
		return err
	}

	// 自动迁移
	if err := DB.AutoMigrate(&model.User{}, &model.Session{}, &model.Article{}); err != nil {
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
