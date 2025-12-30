import type { Article, ArticleDetail, RelatedArticle, PaginatedArticlesResponse } from '@/types/article';
import { buildAuthHeaders, getApiBaseUrl } from '@/services/api';

export async function fetchArticles(token?: string | null) {
  const resp = await fetch(`${getApiBaseUrl()}/articles/`, {
    headers: buildAuthHeaders(token),
  });
  if (!resp.ok) {
    throw new Error('articles fetch failed');
  }
  const data = await resp.json();
  const list = Array.isArray(data?.articles) ? data.articles : [];
  return list as Article[];
}

/** 获取当天最新文章（首页专用） */
export async function fetchTodayArticles(
  token?: string | null
): Promise<PaginatedArticlesResponse> {
  const url = `${getApiBaseUrl()}/articles/today`;
  const resp = await fetch(url, {
    headers: buildAuthHeaders(token),
  });
  if (!resp.ok) {
    throw new Error('today articles fetch failed');
  }
  return (await resp.json()) as PaginatedArticlesResponse;
}

/** 加载更旧的文章（分页） */
export async function fetchArticlesPage(
  beforeDate: string,
  beforeId: number,
  token?: string | null,
  limit: number = 20
): Promise<PaginatedArticlesResponse> {
  const encodedDate = encodeURIComponent(beforeDate);
  const url = `${getApiBaseUrl()}/articles/?v=2&before_date=${encodedDate}&before_id=${beforeId}&limit=${limit}`;
  const resp = await fetch(url, {
    headers: buildAuthHeaders(token),
  });
  if (!resp.ok) {
    throw new Error('paginated articles fetch failed');
  }
  return (await resp.json()) as PaginatedArticlesResponse;
}

export async function fetchArticleDetail(id: number, token?: string | null) {
  const resp = await fetch(`${getApiBaseUrl()}/articles/${id}`, {
    headers: buildAuthHeaders(token),
  });
  if (!resp.ok) {
    throw new Error('article detail fetch failed');
  }
  return (await resp.json()) as ArticleDetail;
}

export function buildArticleFromRelated(article: RelatedArticle): Article {
  return {
    id: article.id,
    title: article.title,
    unit: article.unit,
    published_on: article.published_on,
    summary: article.summary_snippet,
  };
}
