package middleware

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/oap/backend-go/internal/pkg/jwt"
)

func AuthRequired(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		auth := c.GetHeader("Authorization")
		parts := strings.SplitN(strings.TrimSpace(auth), " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") || strings.TrimSpace(parts[1]) == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "未授权访问"})
			return
		}

		token := strings.TrimSpace(parts[1])
		claims, err := jwt.ParseToken(token, jwtSecret)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "未授权访问"})
			return
		}

		c.Set("user_id", claims.Subject)
		c.Set("username", claims.Username)
		c.Set("user_name", claims.Name)
		c.Set("user_roles", claims.Roles)
		c.Next()
	}
}
