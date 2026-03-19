package service

import (
	"testing"
	"time"

	"github.com/oap/backend-go/internal/model"
)

type fakeArticleRepo struct {
	today    []model.Article
	page     []model.Article
	hasOlder bool
}

func (f *fakeArticleRepo) FindToday() ([]model.Article, error) { return f.today, nil }
func (f *fakeArticleRepo) FindPage(beforeDate string, beforeID, limit int) ([]model.Article, error) {
	return f.page, nil
}
func (f *fakeArticleRepo) Count() (int64, error)                      { return 0, nil }
func (f *fakeArticleRepo) FindByID(id uint64) (*model.Article, error) { return nil, nil }
func (f *fakeArticleRepo) HasOlderThan(publishedOn time.Time, id int64) (bool, error) {
	return f.hasOlder, nil
}

func TestGetPage_HasMoreDependsOnWhetherOlderRecordsExist(t *testing.T) {
	repo := &fakeArticleRepo{
		page: []model.Article{
			{ID: 10, PublishedOn: time.Date(2026, 3, 19, 0, 0, 0, 0, time.UTC)},
			{ID: 9, PublishedOn: time.Date(2026, 3, 18, 0, 0, 0, 0, time.UTC)},
		},
		hasOlder: false,
	}
	svc := NewArticleServiceWithRepo(repo)

	result, err := svc.GetPage("2026-03-19", 11, 2)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.HasMore {
		t.Fatalf("expected has_more=false when there are no older records")
	}
}

func TestGetToday_ReturnsCursorWhenOlderRecordsExist(t *testing.T) {
	repo := &fakeArticleRepo{
		today: []model.Article{
			{ID: 100, PublishedOn: time.Date(2026, 3, 19, 0, 0, 0, 0, time.UTC)},
			{ID: 99, PublishedOn: time.Date(2026, 3, 19, 0, 0, 0, 0, time.UTC)},
		},
		hasOlder: true,
	}
	svc := NewArticleServiceWithRepo(repo)

	result, err := svc.GetToday()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !result.HasMore {
		t.Fatalf("expected has_more=true when older records exist")
	}
	if result.NextBeforeID == nil || result.NextBeforeDate == nil {
		t.Fatalf("expected next cursors for today response when has_more=true")
	}
}
