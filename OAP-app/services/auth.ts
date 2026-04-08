import { getApiBaseUrl } from '@/services/api';
import { setAuthToken } from '@/hooks/use-auth-token';
import {
  clearAuthStorage,
  getRefreshToken,
  getUserProfile,
  setRefreshToken,
  setUserProfileRaw,
} from '@/storage/auth-storage';
import { mergeAuthUserIntoProfile } from '@/services/auth-profile-cache';

type RefreshResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: Record<string, unknown>;
};

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshSessionOnForeground() {
  if (refreshInFlight) {
    return await refreshInFlight;
  }

  refreshInFlight = (async () => {
    try {
      const refreshToken = await getRefreshToken();
      if (!refreshToken) {
        return false;
      }

      const resp = await fetch(`${getApiBaseUrl()}/auth/token/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!resp.ok) {
        await clearAuthStorage();
        await setAuthToken(null);
        return false;
      }

      const data = (await resp.json()) as RefreshResponse;
      const mergedProfile = mergeAuthUserIntoProfile(await getUserProfile(), data.user || {});
      await setRefreshToken(data.refresh_token || null);
      await setUserProfileRaw(JSON.stringify(mergedProfile));
      await setAuthToken(data.access_token || null);
      return true;
    } catch (error) {
      console.error('[Auth] Refresh failed:', error);
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return await refreshInFlight;
}
