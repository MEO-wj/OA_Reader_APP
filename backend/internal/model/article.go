package model

import (
	"database/sql/driver"
	"encoding/json"
	"fmt"
	"time"
)

type Article struct {
	ID          uint64    `gorm:"primaryKey"`
	Title       string    `gorm:"not null"`
	Unit        string
	Link        string    `gorm:"uniqueIndex;not null"`
	PublishedOn time.Time `gorm:"index;not null"`
	Content     string    `gorm:"not null"`
	Summary     string    `gorm:"not null"`
	Attachments JSONArray `gorm:"type:jsonb;default:'[]'"`
	CreatedAt   time.Time
	UpdatedAt   time.Time
}

type JSONArray []map[string]string

// Scan 实现 sql.Scanner 接口，从数据库读取 JSONB 字段
func (j *JSONArray) Scan(value interface{}) error {
	if value == nil {
		*j = nil
		return nil
	}

	var data []byte
	switch v := value.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		return fmt.Errorf("cannot scan %T into JSONArray", value)
	}

	if len(data) == 0 {
		*j = nil
		return nil
	}

	return json.Unmarshal(data, j)
}

// Value 实现 driver.Valuer 接口，用于写入数据库
func (j JSONArray) Value() (driver.Value, error) {
	if j == nil {
		return "[]", nil
	}
	return json.Marshal(j)
}
