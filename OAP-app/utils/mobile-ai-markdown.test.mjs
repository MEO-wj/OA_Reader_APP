import test from 'node:test';
import assert from 'node:assert/strict';

import { segmentMarkdownForMobile } from './mobile-ai-markdown.ts';

test('segmentMarkdownForMobile converts markdown tables into article card segments', () => {
  const content = `以下为近期奖学金相关通知：

| 发布日期 | 标题 | 发布单位 | 核心要点 |
| --- | --- | --- | --- |
| 2025-09-11 | 关于开展2024-2025学年本科生国家奖学金评定工作的通知 | 学生处 | 金额10000元/人，名额51名，要求 GPA 与综合素质排名前10% |
| 2025-09-12 | 关于补充提交奖学金材料的说明 | 学生处 | 需在周五前补齐证明材料，逾期不再受理 |

备注：请留意截止时间。`;

  const segments = segmentMarkdownForMobile(content);

  assert.equal(segments.length, 3);
  assert.equal(segments[0].type, 'markdown');
  assert.equal(segments[1].type, 'table_cards');
  assert.equal(segments[2].type, 'markdown');

  const tableSegment = segments[1];
  assert.equal(tableSegment.rows.length, 2);
  assert.equal(tableSegment.rows[0].title, '关于开展2024-2025学年本科生国家奖学金评定工作的通知');
  assert.deepEqual(tableSegment.rows[0].fields, [
    { label: '发布日期', value: '2025-09-11' },
    { label: '发布单位', value: '学生处' },
    { label: '核心要点', value: '金额10000元/人，名额51名，要求 GPA 与综合素质排名前10%' },
  ]);
});

test('segmentMarkdownForMobile keeps plain markdown as a single segment', () => {
  const content = `### 奖学金提醒

请优先关注截止时间，并准备好证明材料。`;

  const segments = segmentMarkdownForMobile(content);

  assert.deepEqual(segments, [
    {
      type: 'markdown',
      content,
    },
  ]);
});

test('segmentMarkdownForMobile ignores table syntax inside fenced code blocks', () => {
  const content = `\`\`\`md
| 标题 | 内容 |
| --- | --- |
| 示例 | 这是代码块 |
\`\`\``;

  const segments = segmentMarkdownForMobile(content);

  assert.deepEqual(segments, [
    {
      type: 'markdown',
      content,
    },
  ]);
});
