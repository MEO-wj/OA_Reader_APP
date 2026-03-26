package middleware

import (
	"crypto/md5"
	"encoding/json"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"
)

func ETAG(c *gin.Context) {
	c.Next()

	if c.Writer.Status() != 200 {
		return
	}

	body, ok := c.Get("response_body")
	if !ok {
		return
	}

	data, _ := json.Marshal(body)
	etag := fmt.Sprintf(`"%x"`, md5.Sum(data))
	c.Header("ETag", etag)
	c.Header("Cache-Control", "max-age=3600, public")

	if c.GetHeader("If-None-Match") == etag {
		c.AbortWithStatus(http.StatusNotModified)
	}
}
