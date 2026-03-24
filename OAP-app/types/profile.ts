export type UserProfile = {
  id?: string;
  username?: string;
  display_name?: string;
  roles?: string[];
  is_vip?: boolean;
  vip_expired_at?: string;
  avatar_url?: string;
  avatar_local_uri?: string;
  profile_tags?: string[];
  bio?: string;
  profile_updated_at?: string;
};

export type UserProfilePatch = Partial<UserProfile>;
