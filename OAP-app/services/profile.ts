import { buildAuthHeaders, getApiBaseUrl } from '@/services/api';
import { getAccessToken } from '@/storage/auth-storage';
import type { UserProfile } from '@/types/profile';

export type ProfileUpdatePayload = Pick<
  UserProfile,
  'display_name' | 'profile_tags' | 'bio' | 'profile_updated_at' | 'avatar_url'
>;

export type ProfileAvatarUploadPayload = {
  uri: string;
  fileName?: string | null;
  mimeType?: string | null;
};

export type ProfileAvatarUploadResponse = {
  avatar_url: string;
};

export const RESERVED_PROFILE_API = {
  getProfile: '/user/profile',
  updateProfile: '/user/profile',
  uploadAvatar: '/user/profile/avatar',
} as const;

export function isProfileRemoteSyncEnabled() {
  return process.env.EXPO_PUBLIC_PROFILE_REMOTE_SYNC === '1';
}

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

export async function fetchReservedProfile() {
  const response = await fetch(`${getApiBaseUrl()}${RESERVED_PROFILE_API.getProfile}`, {
    headers: await buildAuthorizedHeaders(),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as UserProfile;
}

export async function updateReservedProfile(payload: ProfileUpdatePayload) {
  const response = await fetch(`${getApiBaseUrl()}${RESERVED_PROFILE_API.updateProfile}`, {
    method: 'PATCH',
    headers: await buildAuthorizedHeaders(true),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as UserProfile;
}

export async function uploadReservedProfileAvatar(payload: ProfileAvatarUploadPayload) {
  const formData = new FormData();
  formData.append(
    'avatar',
    {
      uri: payload.uri,
      name: payload.fileName || 'avatar.jpg',
      type: payload.mimeType || 'image/jpeg',
    } as any
  );

  const response = await fetch(`${getApiBaseUrl()}${RESERVED_PROFILE_API.uploadAvatar}`, {
    method: 'POST',
    headers: await buildAuthorizedHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await parseErrorMessage(response));
  }

  return (await response.json()) as ProfileAvatarUploadResponse;
}
