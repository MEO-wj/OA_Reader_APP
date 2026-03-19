package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
	jwtpkg "github.com/oap/backend-go/internal/pkg/jwt"
)

func TestAuthRequired_ReturnsPythonUnauthorizedMessage(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/x", AuthRequired("secret"), func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", rec.Code)
	}
	if rec.Body.String() != "{\"error\":\"未授权访问\"}" {
		t.Fatalf("unexpected body: %s", rec.Body.String())
	}
}

func TestAuthRequired_AcceptsLowercaseBearerPrefix(t *testing.T) {
	gin.SetMode(gin.TestMode)
	token, err := jwtpkg.GenerateToken("secret", "u1", "alice", "Alice", []string{"admin"}, 300)
	if err != nil {
		t.Fatalf("generate token failed: %v", err)
	}

	r := gin.New()
	r.GET("/x", AuthRequired("secret"), func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"ok": true})
	})

	req := httptest.NewRequest(http.MethodGet, "/x", nil)
	req.Header.Set("Authorization", "bearer "+token)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", rec.Code, rec.Body.String())
	}
}
