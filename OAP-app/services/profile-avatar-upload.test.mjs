import test from 'node:test';
import assert from 'node:assert/strict';

import { buildAvatarFormValue } from './profile-avatar-upload.ts';

test('buildAvatarFormValue returns web File when provided on web', () => {
  const webFile = new File(['avatar'], 'avatar.png', { type: 'image/png' });

  const result = buildAvatarFormValue(
    {
      uri: 'blob:http://localhost/avatar',
      fileName: 'ignored.png',
      mimeType: 'image/png',
      webFile,
    },
    true
  );

  assert.equal(result, webFile);
});

test('buildAvatarFormValue returns React Native file descriptor on native', () => {
  const result = buildAvatarFormValue(
    {
      uri: 'file:///tmp/avatar.jpg',
      fileName: 'avatar.jpg',
      mimeType: 'image/jpeg',
    },
    false
  );

  assert.deepEqual(result, {
    uri: 'file:///tmp/avatar.jpg',
    name: 'avatar.jpg',
    type: 'image/jpeg',
  });
});
