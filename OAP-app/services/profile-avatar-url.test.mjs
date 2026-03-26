import test from 'node:test';
import assert from 'node:assert/strict';

import { toStoredAvatarUrl } from './profile-avatar-url.ts';

test('toStoredAvatarUrl converts absolute uploaded avatar URL into relative uploads path', () => {
  assert.equal(
    toStoredAvatarUrl('https://api.example.com/uploads/avatars/user-1/avatar.webp'),
    '/uploads/avatars/user-1/avatar.webp'
  );
});

test('toStoredAvatarUrl keeps relative uploads path unchanged', () => {
  assert.equal(
    toStoredAvatarUrl('/uploads/avatars/user-1/avatar.webp'),
    '/uploads/avatars/user-1/avatar.webp'
  );
});

test('toStoredAvatarUrl preserves non-upload external avatar URL', () => {
  assert.equal(
    toStoredAvatarUrl('https://cdn.example.com/avatar/user-1.webp'),
    'https://cdn.example.com/avatar/user-1.webp'
  );
});
