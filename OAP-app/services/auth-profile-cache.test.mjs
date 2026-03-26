import test from 'node:test';
import assert from 'node:assert/strict';

import { mergeAuthUserIntoProfile } from './auth-profile-cache.ts';

test('mergeAuthUserIntoProfile preserves profile fields missing from auth payload', () => {
  const current = {
    id: 'user-1',
    username: '24yhhuang2',
    display_name: '黄应辉',
    avatar_url: 'http://localhost:4420/uploads/avatars/demo/avatar.webp',
    bio: 'bio',
    profile_tags: ['计算机'],
  };

  const next = mergeAuthUserIntoProfile(current, {
    id: 'user-1',
    username: '24yhhuang2',
    display_name: '黄应辉',
    roles: [],
  });

  assert.equal(next.avatar_url, current.avatar_url);
  assert.equal(next.bio, current.bio);
  assert.deepEqual(next.profile_tags, current.profile_tags);
});
