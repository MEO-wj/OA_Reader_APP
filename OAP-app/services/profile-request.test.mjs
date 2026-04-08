import test from 'node:test';
import assert from 'node:assert/strict';

import { requestWithSessionRefresh } from './profile-request.ts';

function createJsonResponse(status, body = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
    },
  });
}

test('requestWithSessionRefresh retries once after refresh succeeds on 401', async () => {
  let attempts = 0;
  let refreshCalls = 0;

  const response = await requestWithSessionRefresh(
    async () => {
      attempts += 1;
      if (attempts === 1) {
        return createJsonResponse(401, { error: 'expired' });
      }
      return createJsonResponse(200, { ok: true });
    },
    async () => {
      refreshCalls += 1;
      return true;
    }
  );

  assert.equal(attempts, 2);
  assert.equal(refreshCalls, 1);
  assert.equal(response.status, 200);
});

test('requestWithSessionRefresh returns original 401 when refresh fails', async () => {
  let attempts = 0;
  let refreshCalls = 0;

  const response = await requestWithSessionRefresh(
    async () => {
      attempts += 1;
      return createJsonResponse(401, { error: 'expired' });
    },
    async () => {
      refreshCalls += 1;
      return false;
    }
  );

  assert.equal(attempts, 1);
  assert.equal(refreshCalls, 1);
  assert.equal(response.status, 401);
});
