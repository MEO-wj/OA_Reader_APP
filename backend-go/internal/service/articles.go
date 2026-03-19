package service

import (
	"time"

	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/repository"
)

type ArticleService struct {
	repo articleRepository
}

type articleRepository interface {
	FindToday() ([]model.Article, error)
	FindPage(beforeDate string, beforeID, limit int) ([]model.Article, error)
	HasOlderThan(publishedOn time.Time, id int64) (bool, error)
	Count() (int64, error)
	FindByID(id uint64) (*model.Article, error)
}

type PaginatedResponse struct {
	Articles       []ArticleDTO `json:"articles"`
	HasMore        bool         `json:"has_more"`
	NextBeforeDate *string      `json:"next_before_date"`
	NextBeforeID   *int64       `json:"next_before_id"`
}

type ArticleDTO struct {
	ID          uint64               `json:"id"`
	Title       string               `json:"title"`
	Unit        string               `json:"unit,omitempty"`
	Link        string               `json:"link,omitempty"`
	PublishedOn string               `json:"published_on,omitempty"`
	Summary     string               `json:"summary,omitempty"`
	Attachments *[]map[string]string `json:"attachments,omitempty"`
}

func NewArticleService() *ArticleService {
	return NewArticleServiceWithRepo(repository.NewArticleRepository())
}

func NewArticleServiceWithRepo(repo articleRepository) *ArticleService {
	return &ArticleService{repo: repo}
}

func (s *ArticleService) GetToday() (*PaginatedResponse, error) {
	articles, err := s.repo.FindToday()
	if err != nil {
		return nil, err
	}
	hasMore, err := s.detectHasMore(articles)
	if err != nil {
		return nil, err
	}
	return s.buildResponse(articles, hasMore), nil
}

func (s *ArticleService) GetPage(beforeDate string, beforeID, limit int) (*PaginatedResponse, error) {
	articles, err := s.repo.FindPage(beforeDate, beforeID, limit)
	if err != nil {
		return nil, err
	}
	hasMore, err := s.detectHasMore(articles)
	if err != nil {
		return nil, err
	}
	return s.buildResponse(articles, hasMore), nil
}

func (s *ArticleService) GetCount() (int64, error) {
	return s.repo.Count()
}

func (s *ArticleService) GetByID(id uint64) (*model.Article, error) {
	return s.repo.FindByID(id)
}

func (s *ArticleService) buildResponse(articles []model.Article, hasMore bool) *PaginatedResponse {
	var nextDate *string
	var nextID *int64

	if hasMore && len(articles) > 0 {
		last := articles[len(articles)-1]
		dateStr := last.PublishedOn.Format("2006-01-02")
		nextDate = &dateStr
		id := int64(last.ID)
		nextID = &id
	}

	dtos := make([]ArticleDTO, len(articles))
	for i, a := range articles {
		dtos[i] = ArticleDTO{
			ID:          a.ID,
			Title:       a.Title,
			Unit:        a.Unit,
			Link:        a.Link,
			PublishedOn: a.PublishedOn.Format("2006-01-02"),
			Summary:     a.Summary,
		}
	}

	return &PaginatedResponse{
		Articles:       dtos,
		HasMore:        hasMore,
		NextBeforeDate: nextDate,
		NextBeforeID:   nextID,
	}
}

func (s *ArticleService) detectHasMore(articles []model.Article) (bool, error) {
	if len(articles) == 0 {
		return false, nil
	}
	last := articles[len(articles)-1]
	return s.repo.HasOlderThan(last.PublishedOn, int64(last.ID))
}
