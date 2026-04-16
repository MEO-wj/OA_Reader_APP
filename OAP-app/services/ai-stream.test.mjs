import test from 'node:test';
import assert from 'node:assert/strict';

import {
  dedupeRelatedArticles,
  extractRelatedArticlesFromToolResult,
} from './ai-stream.ts';

test('extractRelatedArticlesFromToolResult parses search result json and fills summary snippet', () => {
  const articles = extractRelatedArticlesFromToolResult(
    JSON.stringify({
      results: [
        {
          id: 101,
          title: '奖学金评选通知',
          unit: '学生处',
          published_on: '2026-04-16',
          summary: '这是一个很长的摘要，用于验证前端会把 summary 映射成 summary_snippet。',
        },
      ],
    })
  );

  assert.equal(articles.length, 1);
  assert.equal(articles[0].id, 101);
  assert.equal(articles[0].title, '奖学金评选通知');
  assert.equal(articles[0].summary_snippet.includes('这是一个很长的摘要'), true);
});

test('dedupeRelatedArticles merges duplicate ids and keeps first non-empty display fields', () => {
  const deduped = dedupeRelatedArticles([
    {
      id: 101,
      title: '奖学金评选通知',
      unit: '学生处',
      published_on: '2026-04-16',
      similarity: 0.82,
      summary_snippet: '摘要A',
    },
    {
      id: 101,
      title: '',
      unit: '',
      published_on: '',
      similarity: 0.91,
      content_snippet: '正文片段B',
    },
  ]);

  assert.equal(deduped.length, 1);
  assert.equal(deduped[0].title, '奖学金评选通知');
  assert.equal(deduped[0].unit, '学生处');
  assert.equal(deduped[0].published_on, '2026-04-16');
  assert.equal(deduped[0].summary_snippet, '摘要A');
  assert.equal(deduped[0].content_snippet, '正文片段B');
  assert.equal(deduped[0].similarity, 0.91);
});
