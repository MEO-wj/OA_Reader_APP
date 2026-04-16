package middleware

import (
	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/service"
)

// InjectProfile queries user profile from DB and writes to context.
// If user_id is missing, invalid, or profile not found, it silently passes.
func InjectProfile(profileService *service.ProfileService) gin.HandlerFunc {
	return func(c *gin.Context) {
		userIDStr, ok := c.Get("user_id")
		if !ok {
			c.Next()
			return
		}
		userID, err := uuid.Parse(userIDStr.(string))
		if err != nil {
			c.Next()
			return
		}
		profile, err := profileService.GetProfile(userID)
		if err != nil {
			c.Next()
			return
		}
		profileData := map[string]interface{}{
			"display_name": profile.DisplayName,
			"profile_tags": profile.ProfileTags,
			"bio":          profile.Bio,
		}
		c.Set("user_profile", profileData)
		c.Next()
	}
}
