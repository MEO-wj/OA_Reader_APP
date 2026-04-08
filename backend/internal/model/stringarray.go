package model

import (
	"database/sql/driver"
	"fmt"

	"github.com/jackc/pgx/v5/pgtype"
)

type StringArray []string

var postgresTypeMap = pgtype.NewMap()

func (a *StringArray) Scan(value interface{}) error {
	if value == nil {
		*a = nil
		return nil
	}

	var data []byte
	switch v := value.(type) {
	case []byte:
		data = v
	case string:
		data = []byte(v)
	default:
		return fmt.Errorf("cannot scan %T into StringArray", value)
	}

	if len(data) == 0 {
		*a = nil
		return nil
	}

	var arr pgtype.FlatArray[string]
	if err := postgresTypeMap.Scan(pgtype.TextArrayOID, pgtype.TextFormatCode, data, &arr); err != nil {
		return err
	}

	*a = StringArray(arr)
	return nil
}

func (a StringArray) Value() (driver.Value, error) {
	if a == nil {
		return "{}", nil
	}

	buf, err := postgresTypeMap.Encode(pgtype.TextArrayOID, pgtype.TextFormatCode, pgtype.FlatArray[string](a), nil)
	if err != nil {
		return nil, err
	}

	return string(buf), nil
}
