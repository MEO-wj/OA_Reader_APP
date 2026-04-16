export type MobileCardField = {
  label: string;
  value: string;
};

export type MobileTableCardRow = {
  title: string;
  fields: MobileCardField[];
};

export type MobileMarkdownSegment =
  | {
      type: 'markdown';
      content: string;
    }
  | {
      type: 'table_grid';
      headers: string[];
      rows: string[][];
    }
  | {
      type: 'table_cards';
      rows: MobileTableCardRow[];
    };

const TABLE_SEPARATOR_RE = /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/;
const TITLE_HEADER_RE = /标题|主题|名称|事项|文件|文章|通知|帖子/i;
const TABLE_REQUEST_RE =
  /(表格|表形式|列表格|table|markdown table|tabular|按表格|用表格|以表格)/i;
const NOISE_FIELD_RE = /^(序号|编号|序列|no\.?|No\.?)$/i;
const EXPLANATION_LABEL_HEADER_RE = /^(项目|字段|要点|模块|事项|条目|类别|问题|维度|环节|部分|板块|步骤)$/i;
const EXPLANATION_VALUE_HEADER_RE = /^(内容|说明|解读|要求|详情|描述|介绍|答案|结果|分析|做法)$/i;

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function isTableHeader(lines: string[], index: number) {
  if (index + 1 >= lines.length) {
    return false;
  }
  return lines[index].includes('|') && TABLE_SEPARATOR_RE.test(lines[index + 1].trim());
}

function isTableRow(line: string) {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.includes('|')) {
    return false;
  }
  return !TABLE_SEPARATOR_RE.test(trimmed);
}

function isNoiseFieldLabel(label: string) {
  return NOISE_FIELD_RE.test(label.trim());
}

function stripInlineMarkdown(text: string) {
  return text
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#+\s*/, '')
    .replace(/[*_`~]/g, '')
    .trim();
}

function isExplanationTable(headers: string[], rawRows: string[][]) {
  if (headers.length !== 2 || rawRows.length === 0) {
    return false;
  }

  const [labelHeader, valueHeader] = headers.map((header) => stripInlineMarkdown(header));
  if (
    !EXPLANATION_LABEL_HEADER_RE.test(labelHeader) ||
    !EXPLANATION_VALUE_HEADER_RE.test(valueHeader)
  ) {
    return false;
  }

  return rawRows.every((cells) => {
    const label = stripInlineMarkdown(cells[0] ?? '');
    const value = (cells[1] ?? '').trim();
    return label.length > 0 && value.length > 0;
  });
}

function buildExplanationMarkdown(rawRows: string[][]) {
  return rawRows
    .map((cells, index) => {
      const label = stripInlineMarkdown(cells[0] ?? '') || `要点 ${index + 1}`;
      const value = (cells[1] ?? '').trim();
      return value ? `### ${label}\n${value}` : `### ${label}`;
    })
    .join('\n\n')
    .trim();
}

function buildTableRows(headers: string[], rawRows: string[][]): MobileTableCardRow[] {
  const titleIndex = headers.findIndex((header) => TITLE_HEADER_RE.test(header));

  return rawRows.map((cells, index) => {
    const normalizedHeaders = headers.slice(0, cells.length);
    const title =
      (titleIndex >= 0 ? cells[titleIndex] : '') ||
      cells.find((cell) => cell.trim().length > 0) ||
      `条目 ${index + 1}`;

    const fields = normalizedHeaders
      .map((header, fieldIndex) => ({
        label: header || `字段 ${fieldIndex + 1}`,
        value: cells[fieldIndex]?.trim() || '',
      }))
      .filter((field, fieldIndex) => {
        if (!field.value) {
          return false;
        }
        if (fieldIndex === titleIndex && field.value === title) {
          return false;
        }
        if (isNoiseFieldLabel(field.label)) {
          return false;
        }
        return true;
      });

    return { title, fields };
  });
}

export function prefersMarkdownTableRequest(text: string) {
  return TABLE_REQUEST_RE.test(text);
}

export function segmentMarkdownForMobile(
  content: string,
  options?: {
    preserveTables?: boolean;
  }
): MobileMarkdownSegment[] {
  if (!content.trim()) {
    return [{ type: 'markdown', content }];
  }

  const lines = content.split('\n');
  const segments: MobileMarkdownSegment[] = [];
  let markdownBuffer: string[] = [];
  let index = 0;
  let inFence = false;

  const flushMarkdown = () => {
    const buffered = markdownBuffer.join('\n').trim();
    if (buffered) {
      segments.push({ type: 'markdown', content: buffered });
    }
    markdownBuffer = [];
  };

  while (index < lines.length) {
    const trimmed = lines[index].trim();
    if (trimmed.startsWith('```')) {
      inFence = !inFence;
      markdownBuffer.push(lines[index]);
      index += 1;
      continue;
    }

    if (inFence) {
      markdownBuffer.push(lines[index]);
      index += 1;
      continue;
    }

    if (!isTableHeader(lines, index)) {
      markdownBuffer.push(lines[index]);
      index += 1;
      continue;
    }

    const headers = splitTableRow(lines[index]);
    const rawRows: string[][] = [];
    let cursor = index + 2;

    while (cursor < lines.length && isTableRow(lines[cursor])) {
      const cells = splitTableRow(lines[cursor]);
      if (cells.length > 1) {
        rawRows.push(cells);
      }
      cursor += 1;
    }

    if (rawRows.length === 0) {
      markdownBuffer.push(lines[index], lines[index + 1]);
      index += 2;
      continue;
    }

    flushMarkdown();
    if (options?.preserveTables) {
      segments.push({
        type: 'table_grid',
        headers,
        rows: rawRows,
      });
    } else if (isExplanationTable(headers, rawRows)) {
      segments.push({
        type: 'markdown',
        content: buildExplanationMarkdown(rawRows),
      });
    } else {
      segments.push({
        type: 'table_cards',
        rows: buildTableRows(headers, rawRows),
      });
    }
    index = cursor;
  }

  flushMarkdown();
  return segments.length > 0 ? segments : [{ type: 'markdown', content }];
}
