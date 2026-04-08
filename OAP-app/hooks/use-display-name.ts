import { useEffect, useState } from 'react';

import { getUserProfile, subscribeUserProfile } from '@/storage/auth-storage';
import { getDisplayName } from '@/utils/profile';

export function useDisplayName(defaultName = '用户') {
  const [displayName, setDisplayName] = useState<string>(defaultName);

  useEffect(() => {
    const loadDisplayName = async () => {
      const profile = await getUserProfile();
      setDisplayName(getDisplayName(profile, defaultName));
    };

    void loadDisplayName();

    return subscribeUserProfile(() => {
      void loadDisplayName();
    });
  }, [defaultName]);

  return displayName;
}
