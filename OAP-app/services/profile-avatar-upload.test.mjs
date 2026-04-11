import test from 'node:test';
import assert from 'node:assert/strict';

import { buildAvatarFormValue, buildResizeActions } from './profile-avatar-upload.ts';

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

test('buildAvatarFormValue returns React Native file descriptor with WebP defaults on native', () => {
  const result = buildAvatarFormValue(
    {
      uri: 'file:///tmp/avatar.jpg',
    },
    false
  );

  assert.deepEqual(result, {
    uri: 'file:///tmp/avatar.jpg',
    name: 'avatar.webp',
    type: 'image/webp',
  });
});

test('buildResizeActions returns resize to 256x256 and save as WebP quality 80', () => {
  const actions = buildResizeActions();

  assert.equal(actions.length, 2);
  assert.deepEqual(actions[0], { resize: { width: 256, height: 256 } });
  assert.equal(actions[1].save.format, 'webp');
  assert.equal(actions[1].save.quality, 80);
});
