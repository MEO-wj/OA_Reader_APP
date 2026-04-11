import test from 'node:test';
import assert from 'node:assert/strict';

import { getStaticBaseUrl, resolveStaticUrl } from './static-url.ts';

const API_BASE = 'http://localhost:4420/api';

test('getStaticBaseUrl strips /api suffix from API base URL', () => {
  assert.equal(getStaticBaseUrl('http://localhost:4420/api'), 'http://localhost:4420');
});

test('getStaticBaseUrl returns original URL when no /api suffix', () => {
  assert.equal(getStaticBaseUrl('http://localhost:4420'), 'http://localhost:4420');
});

test('getStaticBaseUrl handles production URL with /api', () => {
  assert.equal(getStaticBaseUrl('https://oa-reader.backend.unself.cn/api'), 'https://oa-reader.backend.unself.cn');
});

test('resolveStaticUrl prepends base URL for relative /uploads/ path', () => {
  assert.equal(
    resolveStaticUrl('/uploads/avatars/user-1/avatar.webp', API_BASE),
    'http://localhost:4420/uploads/avatars/user-1/avatar.webp'
  );
});

test('resolveStaticUrl returns absolute URL as-is', () => {
  assert.equal(
    resolveStaticUrl('https://cdn.example.com/avatar/user-1.webp', API_BASE),
    'https://cdn.example.com/avatar/user-1.webp'
  );
});

test('resolveStaticUrl returns null for null input', () => {
  assert.equal(resolveStaticUrl(null, API_BASE), null);
});

test('resolveStaticUrl returns null for empty string', () => {
  assert.equal(resolveStaticUrl('', API_BASE), null);
});
