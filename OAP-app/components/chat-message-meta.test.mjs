import test from 'node:test';
import assert from 'node:assert/strict';

import { getAiMessageMeta } from './chat-message-meta.ts';

test('getAiMessageMeta returns streaming state before first token', () => {
  assert.deepEqual(getAiMessageMeta(true, ''), {
    label: '正在组织回答',
    subtitle: '准备结构与重点',
    tone: 'streaming',
  });
});

test('getAiMessageMeta returns delta streaming state after text arrives', () => {
  assert.deepEqual(getAiMessageMeta(true, '第一段回答'), {
    label: '流式输出中',
    subtitle: '内容正在逐段生成',
    tone: 'streaming',
  });
});

test('getAiMessageMeta returns ready state after generation completes', () => {
  assert.deepEqual(getAiMessageMeta(false, '完整回答'), {
    label: '已整理完成',
    subtitle: '可继续追问或查看来源',
    tone: 'ready',
  });
});

test('getAiMessageMeta returns warning state after stream interruption notice appears', () => {
  assert.deepEqual(getAiMessageMeta(false, '回答片段\n\n（流式输出已中断，可重试继续提问）'), {
    label: '输出已中断',
    subtitle: '可继续追问补全回答',
    tone: 'warning',
  });
});
