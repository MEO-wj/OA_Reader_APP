
import { useEffect, useState } from 'react';
import { useColorScheme as useRNColorScheme, type ColorSchemeName } from 'react-native';

import { getThemePreference, subscribeThemePreference, type ThemePreference } from '@/storage/theme-storage';

export function useColorScheme(): ColorSchemeName {
  const [hasHydrated, setHasHydrated] = useState(false);
  const [preference, setPreference] = useState<ThemePreference>('system');

  useEffect(() => {
    setHasHydrated(true);
  }, []);

  const colorScheme = useRNColorScheme();

  useEffect(() => {
    if (!hasHydrated) {
      return;
    }

    let mounted = true;

    void getThemePreference().then((nextPreference) => {
      if (mounted) {
        setPreference(nextPreference);
      }
    });

    const unsubscribe = subscribeThemePreference((nextPreference) => {
      if (mounted) {
        setPreference(nextPreference);
      }
    });

    return () => {
      mounted = false;
      unsubscribe();
    };
  }, [hasHydrated]);

  if (hasHydrated) {
    if (preference === 'light') {
      return 'light';
    }
    if (preference === 'dark') {
      return 'dark';
    }
    return colorScheme;
  }

  return 'light';
}
