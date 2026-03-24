import { useCallback, useEffect, useState } from 'react';

import type { UserProfile } from '@/types/profile';
import { getUserProfile, subscribeUserProfile } from '@/storage/auth-storage';

export function useUserProfile() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isProfileLoaded, setIsProfileLoaded] = useState(false);

  const reloadProfile = useCallback(async () => {
    const nextProfile = await getUserProfile();
    setProfile(nextProfile);
    setIsProfileLoaded(true);
  }, []);

  useEffect(() => {
    void reloadProfile();
    return subscribeUserProfile(() => {
      void reloadProfile();
    });
  }, [reloadProfile]);

  return {
    profile,
    isProfileLoaded,
    reloadProfile,
  };
}
