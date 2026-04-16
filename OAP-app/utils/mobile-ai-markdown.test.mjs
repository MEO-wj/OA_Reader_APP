import test from 'node:test';
import assert from 'node:assert/strict';

import { prefersMarkdownTableRequest, segmentMarkdownForMobile } from './mobile-ai-markdown.ts';

test('segmentMarkdownForMobile converts markdown tables into article card segments by default', () => {
  const content = `以下是近期奖学金相关通知：
| 发布日期 | 标题 | 发布单位 | 核心要点 |
| --- | --- | --- | --- |
| 2025-09-11 | 关于开展2024-2025学年本科生国家奖学金评定工作的通知 | 学生处 | 金额10000元/人，共51名，要求 GPA 与综合素质排名前10% |
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
    { label: '核心要点', value: '金额10000元/人，共51名，要求 GPA 与综合素质排名前10%' },
  ]);
});

test('segmentMarkdownForMobile converts explanation tables into layered markdown blocks', () => {
  const content = `| 项目 | 内容 |
| --- | --- |
| **奖励对象** | 全日制在校二年级以上（含二年级）品学兼优的本科学生 |
| 申请条件 | 学习成绩与综合素质排名均位于前10% |`;

  const segments = segmentMarkdownForMobile(content);

  assert.deepEqual(segments, [
    {
      type: 'markdown',
      content: `### 奖励对象
全日制在校二年级以上（含二年级）品学兼优的本科学生

### 申请条件
学习成绩与综合素质排名均位于前10%`,
    },
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

test('segmentMarkdownForMobile returns table_grid when caller explicitly requests table rendering', () => {
  const content = `| 日期 | 标题 |
| --- | --- |
| 2026-04-17 | 通知 A |`;

  const segments = segmentMarkdownForMobile(content, { preserveTables: true });

  assert.deepEqual(segments, [
    {
      type: 'table_grid',
      headers: ['日期', '标题'],
      rows: [['2026-04-17', '通知 A']],
    },
  ]);
});

test('segmentMarkdownForMobile filters noise labels such as 序号 in card mode', () => {
  const content = `| 序号 | 标题 | 发布日期 | 核心要点 |
| --- | --- | --- | --- |
| 2 | 关于开展2024-2025学年本科生国家励志奖学金评定工作的通知 | 2025-09-19 | 每人6000元，全校660名，面向家庭经济困难本科生 |`;

  const segments = segmentMarkdownForMobile(content);

  assert.equal(segments.length, 1);
  assert.equal(segments[0].type, 'table_cards');
  assert.deepEqual(segments[0].rows[0].fields, [
    { label: '发布日期', value: '2025-09-19' },
    { label: '核心要点', value: '每人6000元，全校660名，面向家庭经济困难本科生' },
  ]);
});

test('prefersMarkdownTableRequest detects explicit table requests in chinese and english', () => {
  assert.equal(prefersMarkdownTableRequest('请用表格输出最近通知'), true);
  assert.equal(prefersMarkdownTableRequest('use table output to me of recent notices'), true);
  assert.equal(prefersMarkdownTableRequest('帮我总结最近通知'), false);
});
