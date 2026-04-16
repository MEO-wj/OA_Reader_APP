import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveStreamFailure, STREAM_INTERRUPTED_NOTICE } from './use-ai-chat-logic.ts';
import { StreamAbortedError } from '../services/ai-errors.ts';

test('resolveStreamFailure ignores aborted streams', () => {
  const result = resolveStreamFailure({
    receivedDelta: false,
    partialText: '',
    error: new StreamAbortedError(),
    defaultMessage: '默认错误',
  });

  assert.deepEqual(result, { kind: 'ignore' });
});

test('resolveStreamFailure falls back when no delta has arrived', () => {
  const result = resolveStreamFailure({
    receivedDelta: false,
    partialText: '',
    error: new Error('服务异常'),
    defaultMessage: '默认错误',
  });

  assert.deepEqual(result, { kind: 'fallback' });
});

test('resolveStreamFailure keeps partial text and appends interruption notice', () => {
  const result = resolveStreamFailure({
    receivedDelta: true,
    partialText: '已收到的流式内容',
    error: new Error('连接关闭'),
    defaultMessage: '默认错误',
  });

  assert.deepEqual(result, {
    kind: 'show_message',
    message: `已收到的流式内容\n\n${STREAM_INTERRUPTED_NOTICE}`,
  });
});

test('resolveStreamFailure falls back to default message when partial text is empty', () => {
  const result = resolveStreamFailure({
    receivedDelta: true,
    partialText: '   ',
    error: new Error('连接关闭'),
    defaultMessage: '默认错误',
  });

  assert.deepEqual(result, {
    kind: 'show_message',
    message: '默认错误',
  });
});
