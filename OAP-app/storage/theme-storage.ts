import { getItem, removeItem, setItem } from './universal-storage';

export type ThemePreference = 'system' | 'light' | 'dark';

const THEME_PREFERENCE_KEY = 'theme_preference_v1';

let cachedPreference: ThemePreference | null = null;
let hasLoaded = false;

const listeners = new Set<(preference: ThemePreference) => void>();

function parsePreference(raw: string | null): ThemePreference {
  if (raw === 'light' || raw === 'dark' || raw === 'system') {
    return raw;
  }
  return 'system';
}

function notify(preference: ThemePreference) {
  listeners.forEach((listener) => {
    try {
      listener(preference);
    } catch (error) {
      console.error('Theme preference listener failed:', error);
    }
  });
}

export async function getThemePreference(): Promise<ThemePreference> {
  if (hasLoaded && cachedPreference) {
    return cachedPreference;
  }

  const raw = await getItem(THEME_PREFERENCE_KEY);
  const preference = parsePreference(raw);
  cachedPreference = preference;
  hasLoaded = true;
  return preference;
}

export function subscribeThemePreference(listener: (preference: ThemePreference) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function setThemePreference(preference: ThemePreference) {
  cachedPreference = preference;
  hasLoaded = true;
  notify(preference);

  if (preference === 'system') {
    await removeItem(THEME_PREFERENCE_KEY);
    return;
  }
  await setItem(THEME_PREFERENCE_KEY, preference);
}

