package config

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestLoad_UsesEnvironmentWhenDotEnvMissing(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://example")
	t.Setenv("AUTH_JWT_SECRET", "secret")
	t.Setenv("AUTH_REFRESH_HASH_KEY", "refresh")
	t.Setenv("AUTH_ACCESS_TOKEN_TTL", "168h")
	t.Setenv("AUTH_REFRESH_TOKEN_TTL", "336h")
	t.Setenv("AUTH_PASSWORD_COST", "12")
	t.Setenv("AUTH_ALLOW_AUTO_USER_CREATION", "true")
	t.Setenv("CAMPUS_AUTH_ENABLED", "true")
	t.Setenv("CAMPUS_AUTH_URL", "https://example.com/login")
	t.Setenv("CAMPUS_AUTH_TIMEOUT", "10")
	t.Setenv("CORS_ALLOW_ORIGINS", "https://app.example.com,https://admin.example.com")
	t.Setenv("RATE_LIMIT_PER_DAY", "1000")
	t.Setenv("RATE_LIMIT_PER_HOUR", "100")
	t.Setenv("AI_END_URL", "http://ai-end:4421")
	t.Setenv("AUTH_DEBUG", "true")
	t.Setenv("UPLOAD_ROOT_DIR", "/var/lib/oap/uploads")

	cfg, err := Load(filepath.Join(t.TempDir(), ".env"))
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	if cfg.DatabaseURL != "postgres://example" {
		t.Fatalf("unexpected DATABASE_URL: %s", cfg.DatabaseURL)
	}
	wantOrigins := []string{"https://app.example.com", "https://admin.example.com"}
	if !reflect.DeepEqual(cfg.CORSAllowOrigins, wantOrigins) {
		t.Fatalf("unexpected CORS origins: %#v", cfg.CORSAllowOrigins)
	}
	if cfg.UploadRootDir != "/var/lib/oap/uploads" {
		t.Fatalf("unexpected UPLOAD_ROOT_DIR: %s", cfg.UploadRootDir)
	}
}

func TestLoad_ReadsDotEnvWhenPresent(t *testing.T) {
	envPath := filepath.Join(t.TempDir(), ".env")
	content := []byte("DATABASE_URL=postgres://from-file\nAUTH_JWT_SECRET=file-secret\nAUTH_REFRESH_HASH_KEY=file-refresh\nAUTH_ACCESS_TOKEN_TTL=1h\nAUTH_REFRESH_TOKEN_TTL=2h\nAUTH_PASSWORD_COST=10\nAUTH_ALLOW_AUTO_USER_CREATION=false\nCAMPUS_AUTH_ENABLED=false\nCAMPUS_AUTH_URL=https://file.example.com/login\nCAMPUS_AUTH_TIMEOUT=9\nCORS_ALLOW_ORIGINS=https://file.example.com\nRATE_LIMIT_PER_DAY=9\nRATE_LIMIT_PER_HOUR=3\nAI_END_URL=http://file-ai:4421\nAUTH_DEBUG=false\nUPLOAD_ROOT_DIR=/srv/oap/uploads\n")
	if err := os.WriteFile(envPath, content, 0o644); err != nil {
		t.Fatalf("WriteFile: %v", err)
	}

	cfg, err := Load(envPath)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	if cfg.DatabaseURL != "postgres://from-file" {
		t.Fatalf("unexpected DATABASE_URL: %s", cfg.DatabaseURL)
	}
	if cfg.UploadRootDir != "/srv/oap/uploads" {
		t.Fatalf("unexpected UPLOAD_ROOT_DIR: %s", cfg.UploadRootDir)
	}
}

func TestLoad_DefaultPathPrefersParentDotEnv(t *testing.T) {
	rootDir := t.TempDir()
	backendDir := filepath.Join(rootDir, "backend")
	if err := os.MkdirAll(backendDir, 0o755); err != nil {
		t.Fatalf("MkdirAll: %v", err)
	}

	parentEnv := []byte("DATABASE_URL=postgres://parent\nAUTH_JWT_SECRET=secret\nAUTH_REFRESH_HASH_KEY=refresh\nAUTH_ACCESS_TOKEN_TTL=1h\nAUTH_REFRESH_TOKEN_TTL=2h\nAUTH_PASSWORD_COST=10\nAUTH_ALLOW_AUTO_USER_CREATION=false\nCAMPUS_AUTH_ENABLED=false\nCAMPUS_AUTH_URL=https://example.com/login\nCAMPUS_AUTH_TIMEOUT=10\nCORS_ALLOW_ORIGINS=https://parent.example.com\nRATE_LIMIT_PER_DAY=9\nRATE_LIMIT_PER_HOUR=3\nAI_END_URL=http://file-ai:4421\nAUTH_DEBUG=false\nUPLOAD_ROOT_DIR=/srv/oap/uploads\n")
	childEnv := []byte("DATABASE_URL=postgres://child\nAUTH_JWT_SECRET=secret\nAUTH_REFRESH_HASH_KEY=refresh\nAUTH_ACCESS_TOKEN_TTL=1h\nAUTH_REFRESH_TOKEN_TTL=2h\nAUTH_PASSWORD_COST=10\nAUTH_ALLOW_AUTO_USER_CREATION=false\nCAMPUS_AUTH_ENABLED=false\nCAMPUS_AUTH_URL=https://example.com/login\nCAMPUS_AUTH_TIMEOUT=10\nCORS_ALLOW_ORIGINS=https://child.example.com\nRATE_LIMIT_PER_DAY=9\nRATE_LIMIT_PER_HOUR=3\nAI_END_URL=http://file-ai:4421\nAUTH_DEBUG=false\nUPLOAD_ROOT_DIR=/srv/oap/uploads\n")
	if err := os.WriteFile(filepath.Join(rootDir, ".env"), parentEnv, 0o644); err != nil {
		t.Fatalf("WriteFile parent .env: %v", err)
	}
	if err := os.WriteFile(filepath.Join(backendDir, ".env"), childEnv, 0o644); err != nil {
		t.Fatalf("WriteFile backend .env: %v", err)
	}

	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("Getwd: %v", err)
	}
	t.Cleanup(func() {
		_ = os.Chdir(wd)
	})
	if err := os.Chdir(backendDir); err != nil {
		t.Fatalf("Chdir: %v", err)
	}

	cfg, err := Load("")
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.DatabaseURL != "postgres://parent" {
		t.Fatalf("expected parent .env, got %s", cfg.DatabaseURL)
	}
}
