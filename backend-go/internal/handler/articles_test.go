package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestGetPage_RequiresBeforeID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &ArticleHandler{}
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=1&limit=20", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for missing before_id, got %d", rec.Code)
	}
}

func TestGetPage_RejectsInvalidBeforeDateInV2(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &ArticleHandler{}
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=2&before_id=123&before_date=invalid-date", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid before_date, got %d", rec.Code)
	}
}

func TestGetPage_RejectsUnsupportedVersion(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &ArticleHandler{}
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=3&before_id=123", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for unsupported v, got %d", rec.Code)
	}
}

func TestGetPage_RejectsInvalidVersionFormat(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &ArticleHandler{}
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=abc&before_id=123", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid v format, got %d", rec.Code)
	}
}
