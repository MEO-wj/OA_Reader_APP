import type { UserProfile } from '@/types/profile';

export const PROFILE_LIMITS = {
  nameMinLength: 2,
  nameMaxLength: 20,
  tagMinLength: 2,
  tagMaxLength: 10,
  maxTags: 5,
  bioMaxLength: 80,
} as const;

export const PRESET_PROFILE_TAGS = [
  '计算机',
  '自动化',
  '设计',
  '摄影',
  '阅读',
  '效率控',
  '社团人',
  '夜猫子',
] as const;

export function sanitizeDisplayName(value: string) {
  return value.trim();
}

export function sanitizeProfileBio(value: string) {
  return value.trim();
}

export function normalizeProfileTags(tags: string[]) {
  const normalized: string[] = [];
  const seen = new Set<string>();

  for (const rawTag of tags) {
    const tag = rawTag.trim();
    if (!tag) {
      continue;
    }

    const key = tag.toLocaleLowerCase();
    if (seen.has(key)) {
      continue;
    }

    seen.add(key);
    normalized.push(tag);
    if (normalized.length >= PROFILE_LIMITS.maxTags) {
      break;
    }
  }

  return normalized;
}

export function getDisplayName(profile: UserProfile | null | undefined, fallback = '用户') {
  const displayName = profile?.display_name?.trim();
  if (displayName) {
    return displayName;
  }

  const username = profile?.username?.trim();
  if (username) {
    return username;
  }

  return fallback;
}

export function getProfileInitial(profile: UserProfile | null | undefined, fallback = '用户') {
  return getDisplayName(profile, fallback).trim().charAt(0) || '?';
}

export function getProfileAvatarUri(profile: UserProfile | null | undefined) {
  const localUri = profile?.avatar_local_uri?.trim();
  if (localUri) {
    return localUri;
  }

  const remoteUri = profile?.avatar_url?.trim();
  if (remoteUri) {
    return remoteUri;
  }

  return null;
}
