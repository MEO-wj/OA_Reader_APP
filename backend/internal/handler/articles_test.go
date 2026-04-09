package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/service"
)

type fakeArticleRepo struct {
	today          []model.Article
	page           []model.Article
	hasOlder       bool
	findByIDResult *model.Article
	findByIDErr    error
}

func (f *fakeArticleRepo) FindToday() ([]model.Article, error) { return f.today, nil }
func (f *fakeArticleRepo) FindPage(beforeDate string, beforeID, limit int) ([]model.Article, error) {
	return f.page, nil
}
func (f *fakeArticleRepo) FindPageByID(beforeID, limit int) ([]model.Article, error) {
	return f.page, nil
}
func (f *fakeArticleRepo) Count() (int64, error)                       { return 0, nil }
func (f *fakeArticleRepo) FindByID(id uint64) (*model.Article, error) { return f.findByIDResult, f.findByIDErr }
func (f *fakeArticleRepo) HasOlderThan(publishedOn time.Time, id int64) (bool, error) {
	return f.hasOlder, nil
}
func (f *fakeArticleRepo) HasOlderIDThan(id int64) (bool, error) { return f.hasOlder, nil }

func newTestArticleHandler() *ArticleHandler {
	repo := &fakeArticleRepo{
		page: []model.Article{
			{ID: 123, Title: "t1", PublishedOn: time.Date(2026, 3, 19, 0, 0, 0, 0, time.UTC)},
		},
		hasOlder: false,
	}
	svc := service.NewArticleServiceWithRepo(repo)
	return NewArticleHandler(svc)
}

func TestGetPage_V1AcceptsBeforeIDWithoutBeforeDate(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := newTestArticleHandler()
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=1&before_id=200&limit=20", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200 for v=1 without before_date, got %d", rec.Code)
	}
}

func TestGetPage_V2RejectsInvalidBeforeDate(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := newTestArticleHandler()
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=2&before_id=123&before_date=invalid-date", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid before_date, got %d", rec.Code)
	}
}

func TestGetByID_ReturnsSnakeCaseJSONKeys(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &fakeArticleRepo{}
	svc := service.NewArticleServiceWithRepo(repo)
	h := NewArticleHandler(svc)

	// Override FindByID to return a real article
	article := &model.Article{
		ID:          42,
		Title:       "测试标题",
		Unit:        "测试单位",
		Link:        "https://example.com",
		PublishedOn: time.Date(2026, 4, 10, 0, 0, 0, 0, time.UTC),
		Content:     "正文内容",
		Summary:     "AI摘要",
	}
	repo.findByIDResult = article

	r := gin.New()
	r.GET("/api/articles/:id", h.GetByID)

	req := httptest.NewRequest(http.MethodGet, "/api/articles/42", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("failed to parse JSON: %v", err)
	}

	// Verify snake_case keys exist (frontend expects these)
	for _, key := range []string{"id", "title", "unit", "link", "published_on", "content", "summary"} {
		if _, ok := payload[key]; !ok {
			t.Errorf("missing snake_case key %q in response: %v", key, payload)
		}
	}

	// Verify PascalCase keys do NOT exist
	for _, key := range []string{"ID", "Title", "Unit", "Link", "PublishedOn", "Content", "Summary"} {
		if _, ok := payload[key]; ok {
			t.Errorf("unexpected PascalCase key %q in response (should be snake_case)", key)
		}
	}
}

func TestGetPage_RejectsUnsupportedVersion(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := newTestArticleHandler()
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=3&before_id=123", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for unsupported v, got %d", rec.Code)
	}
	var payload map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &payload)
	if payload["error"] != "unsupported v" {
		t.Fatalf("expected unsupported v error, got %v", payload["error"])
	}
}

func TestGetPage_RejectsInvalidVersionFormat(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := newTestArticleHandler()
	r := gin.New()
	r.GET("/api/articles", h.GetPage)

	req := httptest.NewRequest(http.MethodGet, "/api/articles?v=abc&before_id=123", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 for invalid v format, got %d", rec.Code)
	}
	var payload map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &payload)
	if payload["error"] != "invalid v" {
		t.Fatalf("expected invalid v error, got %v", payload["error"])
	}
}
