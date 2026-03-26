import { Platform } from 'react-native';

import { buildAuthHeaders, getApiBaseUrl } from '@/services/api';
import { refreshSessionOnForeground } from '@/services/auth';
import { requestWithSessionRefresh } from '@/services/profile-request';
import { toStoredAvatarUrl } from '@/services/profile-avatar-url';
import { getAccessToken, setUserProfileRaw } from '@/storage/auth-storage';
import type { UserProfile } from '@/types/profile';
import { buildAvatarFormValue } from '@/services/profile-avatar-upload';

export type ProfileUpdatePayload = Pick<
  UserProfile,
  'display_name' | 'profile_tags' | 'bio' | 'profile_updated_at' | 'avatar_url'
>;

export type ProfileAvatarUploadPayload = {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
  webFile?: File | null;
};

export type ProfileAvatarUploadResponse = {
  avatar_url: string;
};

export const PROFILE_API = {
  getProfile: '/user/profile',
  updateProfile: '/user/profile',
  uploadAvatar: '/user/profile/avatar',
} as const;

async function buildAuthorizedHeaders(includeJsonContentType = false) {
  const token = await getAccessToken();
  return {
    ...(includeJsonContentType ? { 'Content-Type': 'application/json' } : {}),
    ...buildAuthHeaders(token),
  };
}

async function parseErrorMessage(response: Response) {
  try {
    const data = await response.json();
    if (typeof data?.error === 'string' && data.error) {
      return data.error;
    }
  } catch {
    // ignore and fall through to generic status error
  }

  return `Profile API request failed with status ${response.status}`;
}

export async function fetchProfile() {
  const response = await requestWithSessionRefresh(
    async () =>
      await fetch(`${getApiBaseUrl()}${PROFILE_API.getProfile}`, {
        headers: await buildAuthorizedHeaders(),
      }),
    refreshSessionOnForeground
  );

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as UserProfile;
}

async function patchProfile(payload: ProfileUpdatePayload) {
  const response = await requestWithSessionRefresh(
    async () =>
      await fetch(`${getApiBaseUrl()}${PROFILE_API.updateProfile}`, {
        method: 'PATCH',
        headers: await buildAuthorizedHeaders(true),
        body: JSON.stringify({
          ...payload,
          avatar_url: toStoredAvatarUrl(payload.avatar_url),
        }),
      }),
    refreshSessionOnForeground
  );

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as UserProfile;
}

async function postProfileAvatar(payload: ProfileAvatarUploadPayload) {
  const formData = new FormData();
  formData.append('avatar', buildAvatarFormValue(payload, Platform.OS === 'web') as any);

  const response = await requestWithSessionRefresh(
    async () =>
      await fetch(`${getApiBaseUrl()}${PROFILE_API.uploadAvatar}`, {
        method: 'POST',
        headers: await buildAuthorizedHeaders(),
        body: formData,
      }),
    refreshSessionOnForeground
  );

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  const result = (await response.json()) as ProfileAvatarUploadResponse;
  return {
    ...result,
    avatar_url: toStoredAvatarUrl(result.avatar_url),
  };
}

export async function refreshProfileCache() {
  const profile = await fetchProfile();
  await setUserProfileRaw(JSON.stringify(profile));
  return profile;
}

export async function updateProfile(payload: ProfileUpdatePayload) {
  const profile = await patchProfile(payload);
  await setUserProfileRaw(JSON.stringify(profile));
  return profile;
}

export async function uploadProfileAvatar(payload: ProfileAvatarUploadPayload) {
  return await postProfileAvatar(payload);
}
