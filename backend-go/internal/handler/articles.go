package handler

import (
	"crypto/md5"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/oap/backend-go/internal/service"
)

type ArticleHandler struct {
	articleService *service.ArticleService
}

func NewArticleHandler(articleService *service.ArticleService) *ArticleHandler {
	return &ArticleHandler{articleService: articleService}
}

func (h *ArticleHandler) GetToday(c *gin.Context) {
	result, err := h.articleService.GetToday()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch articles"})
		return
	}
	h.sendWithETag(c, result)
}

func (h *ArticleHandler) GetPage(c *gin.Context) {
	vStr := c.DefaultQuery("v", "2")
	v, err := strconv.Atoi(vStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid v"})
		return
	}
	if v != 1 && v != 2 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "unsupported v"})
		return
	}

	beforeIDStr := c.Query("before_id")
	if beforeIDStr == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "before_id is required"})
		return
	}
	beforeID, err := strconv.ParseInt(beforeIDStr, 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid before_id"})
		return
	}

	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))

	if v == 1 {
		result, err := h.articleService.GetPageByID(int(beforeID), limit)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch articles"})
			return
		}
		h.sendWithETag(c, result)
		return
	}

	beforeDate := c.Query("before_date")
	if beforeDate == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "before_date is required"})
		return
	}
	if _, err := time.Parse("2006-01-02", beforeDate); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid before_date"})
		return
	}

	result, err := h.articleService.GetPage(beforeDate, int(beforeID), limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to fetch articles"})
		return
	}
	h.sendWithETag(c, result)
}

func (h *ArticleHandler) GetCount(c *gin.Context) {
	count, err := h.articleService.GetCount()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to count articles"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"total": count})
}

func (h *ArticleHandler) GetByID(c *gin.Context) {
	id, err := strconv.ParseUint(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid id"})
		return
	}

	article, err := h.articleService.GetByID(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "article not found"})
		return
	}

	c.JSON(http.StatusOK, article)
}

func (h *ArticleHandler) sendWithETag(c *gin.Context, data interface{}) {
	jsonBytes, _ := json.Marshal(data)
	etag := fmt.Sprintf(`"%x"`, md5.Sum(jsonBytes))

	if c.GetHeader("If-None-Match") == etag {
		c.AbortWithStatus(http.StatusNotModified)
		return
	}

	c.Header("ETag", etag)
	c.Header("Cache-Control", "max-age=3600, public")
	c.JSON(http.StatusOK, data)
}
