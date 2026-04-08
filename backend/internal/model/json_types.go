package model

import (
	"database/sql/driver"
	"encoding/json"
	"fmt"
)

type JSONMap map[string]any

// Scan 实现 sql.Scanner 接口，从数据库读取 JSONB 字段
func (m *JSONMap) Scan(value interface{}) error {
	if value == nil {
		*m = nil
		return nil
	}

	var data []byte
	switch v := value.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		return fmt.Errorf("cannot scan %T into JSONMap", value)
	}

	if len(data) == 0 {
		*m = nil
		return nil
	}

	return json.Unmarshal(data, m)
}

// Value 实现 driver.Valuer 接口，用于写入数据库
func (m JSONMap) Value() (driver.Value, error) {
	if m == nil {
		return "{}", nil
	}
	return json.Marshal(m)
}
