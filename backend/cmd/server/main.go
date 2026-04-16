package main

import (
	"log"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"

	"github.com/oap/backend-go/internal/config"
	"github.com/oap/backend-go/internal/handler"
	"github.com/oap/backend-go/internal/middleware"
	"github.com/oap/backend-go/internal/migration"
	"github.com/oap/backend-go/internal/pkg/alog"
	"github.com/oap/backend-go/internal/repository"
	"github.com/oap/backend-go/internal/service"
)

func main() {
	// 加载配置
	cfg, err := config.Load("")
	if err != nil {
		log.Fatal("Failed to load config:", err)
	}

	// 初始化数据库
	if err := repository.InitDB(cfg.DatabaseURL); err != nil {
		log.Fatal("Failed to init db:", err)
	}
	if err := migration.Run(repository.GetDB()); err != nil {
		log.Fatal("Failed to run migrations:", err)
	}
	alog.SetAuthDebug(cfg.AuthDebug)

	// 初始化服务
	authService := service.NewAuthService(cfg)
	articleService := service.NewArticleService()
	profileService := service.NewProfileService(repository.NewUserRepository())

	aiQueue := handler.NewAIRequestQueue(2)
	defer aiQueue.Close()

	// 初始化处理器
	authHandler := handler.NewAuthHandler(authService)
	articleHandler := handler.NewArticleHandler(articleService)
	profileHandler := handler.NewProfileHandlerWithUploadRoot(profileService, cfg.UploadRootDir)
	aiHandler := handler.NewAIHandler(cfg.AIEndURL, aiQueue)

	// Gin 路由
	r := gin.Default()

	// CORS
	r.Use(cors.New(newCORSConfig(cfg)))
	r.Static("/uploads", cfg.UploadRootDir)

	// 健康检查
	r.GET("/api/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	// 认证路由
	auth := r.Group("/api/auth")
	{
		auth.POST("/token", authHandler.Login)
		auth.GET("/me", middleware.AuthRequired(cfg.AuthJWTSecret), authHandler.Me)
	}

	// 文章路由
	articles := r.Group("/api/articles")
	{
		articles.GET("/today", articleHandler.GetToday)
		articles.GET("/", articleHandler.GetPage)
		articles.GET("/count", articleHandler.GetCount)
		articles.GET("/:id", articleHandler.GetByID)
	}

	user := r.Group("/api/user")
	user.Use(middleware.AuthRequired(cfg.AuthJWTSecret))
	{
		user.GET("/profile", profileHandler.GetProfile)
		user.PATCH("/profile", profileHandler.UpdateProfile)
		user.POST("/profile/avatar", profileHandler.UploadAvatar)
	}

	// AI 路由 (需要认证)
	ai := r.Group("/api/ai")
	ai.Use(middleware.AuthRequired(cfg.AuthJWTSecret))
	ai.Use(middleware.InjectProfile(profileService))
	{
		ai.POST("/chat", aiHandler.Chat)
		ai.POST("/ask", aiHandler.Ask)
		ai.POST("/clear_memory", aiHandler.ClearMemory)
		ai.POST("/embed", aiHandler.Embed)
	}

	log.Println("Server starting on :4420")
	r.Run(":4420")
}

func newCORSConfig(cfg *config.Config) cors.Config {
	return cors.Config{
		AllowOrigins:     cfg.CORSAllowOrigins,
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization"},
		ExposeHeaders:    []string{"Content-Length", "ETag"},
		AllowCredentials: false,
	}
}
