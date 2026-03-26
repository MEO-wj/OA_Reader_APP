package service

import (
	"errors"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/oap/backend-go/internal/model"
	"github.com/oap/backend-go/internal/repository"
)

type ProfileUpdateInput = repository.ProfileUpdateInput

type UserProfile struct {
	ID               string     `json:"id"`
	Username         string     `json:"username"`
	DisplayName      string     `json:"display_name"`
	Roles            []string   `json:"roles"`
	AvatarURL        string     `json:"avatar_url,omitempty"`
	ProfileTags      []string   `json:"profile_tags"`
	Bio              string     `json:"bio"`
	ProfileUpdatedAt *time.Time `json:"profile_updated_at"`
	IsVIP            bool       `json:"is_vip"`
	VIPExpiredAt     *time.Time `json:"vip_expired_at"`
}

type profileRepository interface {
	FindByID(id uuid.UUID) (*model.User, error)
	UpdateProfileByID(id uuid.UUID, input repository.ProfileUpdateInput) (*model.User, error)
}

type ProfileService struct {
	repo profileRepository
}

func NewProfileService(repo profileRepository) *ProfileService {
	return &ProfileService{repo: repo}
}

func (s *ProfileService) GetProfile(userID uuid.UUID) (*UserProfile, error) {
	user, err := s.repo.FindByID(userID)
	if err != nil {
		return nil, err
	}
	return toUserProfile(user), nil
}

func (s *ProfileService) UpdateProfile(userID uuid.UUID, input ProfileUpdateInput) (*UserProfile, error) {
	displayName := strings.TrimSpace(input.DisplayName)
	bio := strings.TrimSpace(input.Bio)
	avatarURL := strings.TrimSpace(input.AvatarURL)
	profileTags, err := normalizeProfileTags(input.ProfileTags)
	if err != nil {
		return nil, err
	}

	if err := validateDisplayName(displayName); err != nil {
		return nil, err
	}
	if utf8.RuneCountInString(bio) > 80 {
		return nil, validationError{message: "bio too long"}
	}

	if input.ProfileUpdatedAt.IsZero() {
		input.ProfileUpdatedAt = time.Now().UTC()
	}
	input.DisplayName = displayName
	input.Bio = bio
	input.AvatarURL = avatarURL
	input.ProfileTags = profileTags

	user, err := s.repo.UpdateProfileByID(userID, input)
	if err != nil {
		return nil, err
	}
	return toUserProfile(user), nil
}

func validateDisplayName(displayName string) error {
	length := utf8.RuneCountInString(displayName)
	if length < 2 || length > 20 {
		return validationError{message: "display_name length must be between 2 and 20"}
	}
	return nil
}

func normalizeProfileTags(tags []string) ([]string, error) {
	if len(tags) > 5 {
		return nil, validationError{message: "too many profile_tags"}
	}

	seen := map[string]bool{}
	normalized := make([]string, 0, len(tags))
	for _, raw := range tags {
		tag := strings.TrimSpace(raw)
		if tag == "" {
			continue
		}
		length := utf8.RuneCountInString(tag)
		if length < 2 || length > 10 {
			return nil, validationError{message: "profile_tag length must be between 2 and 10"}
		}
		key := strings.ToLower(tag)
		if seen[key] {
			continue
		}
		seen[key] = true
		normalized = append(normalized, tag)
	}
	return normalized, nil
}

func toUserProfile(user *model.User) *UserProfile {
	if user == nil {
		return nil
	}
	return &UserProfile{
		ID:               user.ID.String(),
		Username:         user.Username,
		DisplayName:      user.DisplayName,
		Roles:            append([]string{}, []string(user.Roles)...),
		AvatarURL:        user.AvatarURL,
		ProfileTags:      append([]string{}, []string(user.ProfileTags)...),
		Bio:              user.Bio,
		ProfileUpdatedAt: user.ProfileUpdatedAt,
		IsVIP:            user.IsVIP,
		VIPExpiredAt:     user.VIPExpiredAt,
	}
}

func IsProfileNotFound(err error) bool {
	return errors.Is(err, repository.ErrNotFound)
}
