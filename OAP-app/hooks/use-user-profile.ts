import { useCallback, useEffect, useState } from 'react';

import { refreshProfileCache } from '@/services/profile';
import type { UserProfile } from '@/types/profile';
import { getUserProfile, subscribeUserProfile } from '@/storage/auth-storage';

export function useUserProfile() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [isProfileLoaded, setIsProfileLoaded] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

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

  const syncProfileFromRemote = useCallback(async () => {
    setIsSyncing(true);
    setSyncError(null);
    try {
      const nextProfile = await refreshProfileCache();
      setProfile(nextProfile);
      setIsProfileLoaded(true);
      return nextProfile;
    } catch (error) {
      const message = error instanceof Error ? error.message : '资料同步失败';
      setSyncError(message);
      throw error;
    } finally {
      setIsSyncing(false);
    }
  }, []);

  return {
    profile,
    isProfileLoaded,
    isSyncing,
    syncError,
    reloadProfile,
    syncProfileFromRemote,
  };
}
