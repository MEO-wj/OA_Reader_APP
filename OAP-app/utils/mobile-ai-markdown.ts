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
      type: 'table_cards';
      rows: MobileTableCardRow[];
    };

const TABLE_SEPARATOR_RE = /^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/;
const TITLE_HEADER_RE = /标题|主题|名称|事项|文件|文章|通知|帖子/i;

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
        return true;
      });

    return { title, fields };
  });
}

export function segmentMarkdownForMobile(content: string): MobileMarkdownSegment[] {
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
    segments.push({
      type: 'table_cards',
      rows: buildTableRows(headers, rawRows),
    });
    index = cursor;
  }

  flushMarkdown();
  return segments.length > 0 ? segments : [{ type: 'markdown', content }];
}
