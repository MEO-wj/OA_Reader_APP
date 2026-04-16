import type { RelatedArticle } from '@/types/article';

const SCORE_FIELDS = ['ebd_similarity', 'keyword_similarity', 'rerank_score'] as const;

type ScoreField = (typeof SCORE_FIELDS)[number];

type ToolResultDoc = Partial<RelatedArticle> &
  Partial<Record<ScoreField, number>> &
  Record<string, unknown>;

function truncateText(text: string | undefined, limit = 80) {
  if (!text) {
    return '';
  }
  const normalized = text.split(/\s+/).filter(Boolean).join(' ');
  if (normalized.length <= limit) {
    return normalized;
  }
  return `${normalized.slice(0, limit).trimEnd()}...`;
}

function toFiniteNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function pickSimilarity(doc: ToolResultDoc) {
  for (const field of SCORE_FIELDS) {
    const value = toFiniteNumber(doc[field]);
    if (value !== null) {
      return value;
    }
  }
  return toFiniteNumber(doc.similarity) ?? undefined;
}

function toToolResultDocs(parsed: unknown): ToolResultDoc[] {
  if (Array.isArray(parsed)) {
    return parsed.filter((item): item is ToolResultDoc => !!item && typeof item === 'object');
  }
  if (parsed && typeof parsed === 'object') {
    const results = (parsed as { results?: unknown }).results;
    if (Array.isArray(results)) {
      return results.filter((item): item is ToolResultDoc => !!item && typeof item === 'object');
    }
    return [parsed as ToolResultDoc];
  }
  return [];
}

function toRelatedArticle(doc: ToolResultDoc): RelatedArticle | null {
  if (typeof doc.id !== 'number' || !Number.isFinite(doc.id)) {
    return null;
  }
  if (typeof doc.title !== 'string' || !doc.title.trim()) {
    return null;
  }

  return {
    id: doc.id,
    title: doc.title,
    unit: typeof doc.unit === 'string' && doc.unit ? doc.unit : undefined,
    published_on: typeof doc.published_on === 'string' && doc.published_on ? doc.published_on : undefined,
    similarity: pickSimilarity(doc),
    content_snippet:
      typeof doc.content_snippet === 'string' && doc.content_snippet ? doc.content_snippet : undefined,
    summary_snippet:
      typeof doc.summary_snippet === 'string' && doc.summary_snippet
        ? doc.summary_snippet
        : truncateText(typeof doc.summary === 'string' ? doc.summary : undefined),
  };
}

export function extractRelatedArticlesFromToolResult(rawResult: unknown): RelatedArticle[] {
  let parsed = rawResult;
  if (typeof rawResult === 'string') {
    try {
      parsed = JSON.parse(rawResult);
    } catch {
      return [];
    }
  }

  return toToolResultDocs(parsed)
    .map(toRelatedArticle)
    .filter((item): item is RelatedArticle => !!item);
}

export function dedupeRelatedArticles(articles: RelatedArticle[]): RelatedArticle[] {
  const merged = new Map<number, RelatedArticle>();

  for (const article of articles) {
    const existing = merged.get(article.id);
    if (!existing) {
      merged.set(article.id, { ...article });
      continue;
    }

    merged.set(article.id, {
      ...existing,
      title: existing.title || article.title,
      unit: existing.unit || article.unit,
      published_on: existing.published_on || article.published_on,
      content_snippet: existing.content_snippet || article.content_snippet,
      summary_snippet: existing.summary_snippet || article.summary_snippet,
      similarity:
        typeof article.similarity === 'number'
          ? Math.max(existing.similarity ?? Number.NEGATIVE_INFINITY, article.similarity)
          : existing.similarity,
    });
  }

  return Array.from(merged.values());
}
