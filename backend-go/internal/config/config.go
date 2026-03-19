package config

import (
	"time"

	"github.com/spf13/viper"
)

type Config struct {
	DatabaseURL         string        `mapstructure:"DATABASE_URL"`
	AuthJWTSecret       string        `mapstructure:"AUTH_JWT_SECRET"`
	AuthRefreshHashKey  string        `mapstructure:"AUTH_REFRESH_HASH_KEY"`
	AuthAccessTokenTTL  time.Duration `mapstructure:"AUTH_ACCESS_TOKEN_TTL"`
	AuthRefreshTokenTTL time.Duration `mapstructure:"AUTH_REFRESH_TOKEN_TTL"`
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
}

func Load(path string) (*Config, error) {
	viper.SetConfigFile(path)

	if err := viper.ReadInConfig(); err != nil {
		return nil, err
	}

	var cfg Config
	if err := viper.Unmarshal(&cfg); err != nil {
		return nil, err
	}
	return &cfg, nil
}
