package repository

import (
	"database/sql"
	"time"

	"github.com/oap/backend-go/internal/model"
	"gorm.io/gorm"
)

type ArticleRepository struct {
	db *gorm.DB
}

func NewArticleRepository() *ArticleRepository {
	return &ArticleRepository{db: GetDB()}
}

func (r *ArticleRepository) FindToday() ([]model.Article, error) {
	var articles []model.Article
	loc := time.Now().Location()
	todayStart, tomorrowStart := localDayRange(time.Now(), loc)

	// 先查今天的数据
	if err := r.db.Where("published_on >= ? AND published_on < ?", todayStart, tomorrowStart).
		Order("published_on DESC, id DESC").
		Find(&articles).Error; err != nil {
		return nil, err
	}

	// 今天没数据，回退到最新有数据的日期
	if len(articles) == 0 {
		var latestDate sql.NullTime
		if err := r.db.Model(&model.Article{}).
			Select("MAX(published_on)").
			Scan(&latestDate).Error; err != nil {
			return nil, err
		}
		if latestDate.Valid {
			latestDayStart, nextDayStart := localDayRange(latestDate.Time, loc)
			if err := r.db.Where("published_on >= ? AND published_on < ?", latestDayStart, nextDayStart).
				Order("published_on DESC, id DESC").
				Find(&articles).Error; err != nil {
				return nil, err
			}
		}
	}

	return articles, nil
}

func localDayStart(t time.Time, loc *time.Location) time.Time {
	local := t.In(loc)
	year, month, day := local.Date()
	return time.Date(year, month, day, 0, 0, 0, 0, loc)
}

func localDayRange(t time.Time, loc *time.Location) (time.Time, time.Time) {
	start := localDayStart(t, loc)
	return start, start.AddDate(0, 0, 1)
}

func (r *ArticleRepository) FindPage(beforeDate string, beforeID, limit int) ([]model.Article, error) {
	var articles []model.Article
	date, err := time.Parse("2006-01-02", beforeDate)
	if err != nil {
		return nil, err
	}
	if err := r.db.Where("(published_on, id) < (?, ?)", date, beforeID).
		Order("published_on DESC, id DESC").
		Limit(limit).
		Find(&articles).Error; err != nil {
		return nil, err
	}
	return articles, nil
}

func (r *ArticleRepository) FindPageByID(beforeID, limit int) ([]model.Article, error) {
	var articles []model.Article
	if err := r.db.Where("id < ?", beforeID).
		Order("id DESC").
		Limit(limit).
		Find(&articles).Error; err != nil {
		return nil, err
	}
	return articles, nil
}

func (r *ArticleRepository) HasOlderThan(publishedOn time.Time, id int64) (bool, error) {
	err := r.db.Model(&model.Article{}).
		Where("(published_on, id) < (?, ?)", publishedOn, id).
		Take(&model.Article{}).Error
	if err == gorm.ErrRecordNotFound {
		return false, nil
	}
	return err == nil, err
}

func (r *ArticleRepository) HasOlderIDThan(id int64) (bool, error) {
	err := r.db.Model(&model.Article{}).
		Where("id < ?", id).
		Take(&model.Article{}).Error
	if err == gorm.ErrRecordNotFound {
		return false, nil
	}
	return err == nil, err
}

func (r *ArticleRepository) Count() (int64, error) {
	var count int64
	if err := r.db.Model(&model.Article{}).Count(&count).Error; err != nil {
		return 0, err
	}
	return count, nil
}

func (r *ArticleRepository) FindByID(id uint64) (*model.Article, error) {
	var article model.Article
	if err := r.db.First(&article, id).Error; err != nil {
		return nil, err
	}
	return &article, nil
}
