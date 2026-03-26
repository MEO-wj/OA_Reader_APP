import type { UserProfile, UserProfilePatch } from '@/types/profile';

export function mergeAuthUserIntoProfile(
  current: UserProfile | null | undefined,
  authUser: UserProfilePatch | null | undefined
): UserProfile {
  return {
    ...(current ?? {}),
    ...(authUser ?? {}),
  };
}
