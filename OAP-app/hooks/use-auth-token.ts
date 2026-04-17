
import { useEffect, useSyncExternalStore } from 'react';

import { getAccessToken, setAccessToken } from '@/storage/auth-storage';

type AuthState = {
  token: string | null;
  isLoading: boolean;
};

const listeners = new Set<() => void>();
let authState: AuthState = { token: null, isLoading: true };

function notify() {
  listeners.forEach((listener) => {
    try {
      listener();
    } catch (error) {
      console.error('Auth listener error:', error);
    }
  });
}

export function subscribeAuthToken(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getAuthSnapshot() {
  return authState;
}

export async function loadAuthToken() {
  let token: string | null = null;

  try {
    token = await getAccessToken();
  } catch (error) {
    console.error('Failed to read token from storage:', error);
    token = null;
  }

  authState = { token, isLoading: false };
  notify();
}

export async function setAuthToken(token: string | null) {
  try {
    await setAccessToken(token);
  } catch (error) {
    console.error('Failed to save token to storage:', error);
  }

  authState = { token, isLoading: false };
  notify();
}

export async function clearAuthToken() {
  await setAuthToken(null);
}

export function useAuthTokenState() {
  const state = useSyncExternalStore(subscribeAuthToken, getAuthSnapshot, getAuthSnapshot);

  useEffect(() => {
    if (state.isLoading) {
      void loadAuthToken();
    }
  }, [state.isLoading]);

  return {
    ...state,
    setAuthToken,
    clearAuthToken,
    loadAuthToken,
  };
}

export function useAuthToken() {
  const { token } = useAuthTokenState();
  return token;
}
