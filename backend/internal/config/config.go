package config

import (
	"os"
	"strings"
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	DatabaseURL         string        `mapstructure:"DATABASE_URL"`
	AuthJWTSecret       string        `mapstructure:"AUTH_JWT_SECRET"`
	AuthAccessTokenTTL  time.Duration `mapstructure:"AUTH_ACCESS_TOKEN_TTL"`
	AuthPasswordCost    int           `mapstructure:"AUTH_PASSWORD_COST"`
	AuthAllowAutoUser   bool          `mapstructure:"AUTH_ALLOW_AUTO_USER_CREATION"`
	CampusAuthEnabled   bool          `mapstructure:"CAMPUS_AUTH_ENABLED"`
	CampusAuthURL       string        `mapstructure:"CAMPUS_AUTH_URL"`
	CampusAuthTimeout   int           `mapstructure:"CAMPUS_AUTH_TIMEOUT"`
	CORSAllowOrigins    []string      `mapstructure:"CORS_ALLOW_ORIGINS"`
	RateLimitPerDay     int           `mapstructure:"RATE_LIMIT_PER_DAY"`
	RateLimitPerHour    int           `mapstructure:"RATE_LIMIT_PER_HOUR"`
	AIEndURL            string        `mapstructure:"AI_END_URL"`
	AuthDebug           bool          `mapstructure:"AUTH_DEBUG"`
	UploadRootDir       string        `mapstructure:"UPLOAD_ROOT_DIR"`
}

func Load(path string) (*Config, error) {
	if strings.TrimSpace(path) == "" {
		path = discoverDefaultEnvPath()
	}

	v := viper.New()
	v.SetConfigFile(path)
	v.AutomaticEnv()
	for _, key := range []string{
		"DATABASE_URL",
		"AUTH_JWT_SECRET",
		"AUTH_ACCESS_TOKEN_TTL",
		"AUTH_PASSWORD_COST",
		"AUTH_ALLOW_AUTO_USER_CREATION",
		"CAMPUS_AUTH_ENABLED",
		"CAMPUS_AUTH_URL",
		"CAMPUS_AUTH_TIMEOUT",
		"CORS_ALLOW_ORIGINS",
		"RATE_LIMIT_PER_DAY",
		"RATE_LIMIT_PER_HOUR",
		"AI_END_URL",
		"AUTH_DEBUG",
		"UPLOAD_ROOT_DIR",
	} {
		if err := v.BindEnv(key); err != nil {
			return nil, err
		}
	}

	if _, err := os.Stat(path); err == nil {
		if err := v.ReadInConfig(); err != nil {
			return nil, err
		}
	}

	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, err
	}
	if len(cfg.CORSAllowOrigins) == 0 {
		cfg.CORSAllowOrigins = splitAndTrim(v.GetString("CORS_ALLOW_ORIGINS"))
	}
	cfg.UploadRootDir = strings.TrimSpace(cfg.UploadRootDir)
	if cfg.UploadRootDir == "" {
		cfg.UploadRootDir = "uploads"
	}
	return &cfg, nil
}

func discoverDefaultEnvPath() string {
	for _, candidate := range []string{"../.env", ".env"} {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return ".env"
}

func splitAndTrim(raw string) []string {
	if raw == "" {
		return nil
	}

	parts := strings.Split(raw, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		trimmed := strings.TrimSpace(part)
		if trimmed != "" {
			values = append(values, trimmed)
		}
	}
	return values
}
