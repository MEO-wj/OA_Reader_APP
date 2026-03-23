// 认证存储工具：双端适配（App 用 SecureStore，Web 用 localStorage）

import * as ExpoSecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import type { UserProfile, UserProfilePatch } from '@/types/profile';

type SecureStoreModule = typeof ExpoSecureStore;

const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const USER_PROFILE_KEY = 'user_profile';

const isWebEnv = Platform.OS === 'web';
const userProfileListeners = new Set<() => void>();
let SecureStore: SecureStoreModule | null = null;

if (!isWebEnv) {
  SecureStore = ExpoSecureStore;
}

async function getItem(key: string) {
  try {
    if (!isWebEnv && SecureStore) {
      return await SecureStore.getItemAsync(key);
    }
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem(key);
    }
  } catch (error) {
    console.error('Failed to read auth storage:', error);
  }
  return null;
}

async function setItem(key: string, value: string) {
  try {
    if (!isWebEnv && SecureStore) {
      await SecureStore.setItemAsync(key, value);
      return;
    }
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(key, value);
    }
  } catch (error) {
    console.error('Failed to write auth storage:', error);
  }
}

async function removeItem(key: string) {
  try {
    if (!isWebEnv && SecureStore) {
      await SecureStore.deleteItemAsync(key);
      return;
    }
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem(key);
    }
  } catch (error) {
    console.error('Failed to remove auth storage:', error);
  }
}

function emitUserProfileChanged() {
  userProfileListeners.forEach((listener) => {
    try {
      listener();
    } catch (error) {
      console.error('Failed to notify user profile listener:', error);
    }
  });
}

export async function getAccessToken() {
  return await getItem(ACCESS_TOKEN_KEY);
}

export async function setAccessToken(token: string | null) {
  if (token) {
    await setItem(ACCESS_TOKEN_KEY, token);
    return;
  }
  await removeItem(ACCESS_TOKEN_KEY);
}

export async function getRefreshToken() {
  return await getItem(REFRESH_TOKEN_KEY);
}

export async function setRefreshToken(token: string | null) {
  if (token) {
    await setItem(REFRESH_TOKEN_KEY, token);
    return;
  }
  await removeItem(REFRESH_TOKEN_KEY);
}

export async function getUserProfileRaw() {
  return await getItem(USER_PROFILE_KEY);
}

export async function getUserProfile() {
  const value = await getUserProfileRaw();
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value) as UserProfile;
  } catch (error) {
    console.error('Failed to parse user profile:', error);
    return null;
  }
}

export async function setUserProfileRaw(value: string | null) {
  if (value) {
    await setItem(USER_PROFILE_KEY, value);
    emitUserProfileChanged();
    return;
  }
  await removeItem(USER_PROFILE_KEY);
  emitUserProfileChanged();
}

export async function updateUserProfile(patch: UserProfilePatch) {
  const current = (await getUserProfile()) ?? {};
  const nextProfile = {
    ...current,
    ...patch,
  } satisfies UserProfile;

  await setUserProfileRaw(JSON.stringify(nextProfile));
  return nextProfile;
}

export function subscribeUserProfile(listener: () => void) {
  userProfileListeners.add(listener);
  return () => {
    userProfileListeners.delete(listener);
  };
}

export async function clearAuthStorage() {
  await Promise.all([
    removeItem(ACCESS_TOKEN_KEY),
    removeItem(REFRESH_TOKEN_KEY),
    removeItem(USER_PROFILE_KEY),
  ]);
  emitUserProfileChanged();
}
