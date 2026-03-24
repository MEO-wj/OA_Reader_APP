import type { Article, ArticleDetail } from '@/types/article';
import {
  getAllKeys,
  getItem,
  multiGet,
  multiRemove,
  removeItem,
  setItem,
} from '@/storage/universal-storage';

const DAY_KEY_PREFIX = 'articles.day.';
const DETAIL_KEY_PREFIX = 'articles.detail.';
const PAGINATION_KEY = 'articles.pagination.state';

type CachedDay = {
  date: string;
  cached_at: number;
  articles: Article[];
};

type CachedDetail = {
  cached_at: number;
  published_on?: string;
  detail: ArticleDetail;
};

/** 分页状态存储 */
export type PaginationState = {
  next_before_date: string | null;
  next_before_id: number | null;
  has_more: boolean;
  updated_at: number;
};

export function getTodayDateString() {
  return new Date().toISOString().slice(0, 10);
}

function dayKey(dateStr: string) {
  return `${DAY_KEY_PREFIX}${dateStr}`;
}

function detailKey(id: number) {
  return `${DETAIL_KEY_PREFIX}${id}`;
}

/** 获取分页状态 */
export async function getPaginationState(): Promise<PaginationState | null> {
  const raw = await getItem(PAGINATION_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as PaginationState;
  } catch {
    return null;
  }
}

/** 保存分页状态 */
export async function setPaginationState(state: PaginationState) {
  await setItem(
    PAGINATION_KEY,
    JSON.stringify({ ...state, updated_at: Date.now() })
  );
}

/** 清除分页状态 */
export async function clearPaginationState() {
  await removeItem(PAGINATION_KEY);
}

export async function pruneArticleCache() {
  const keys = await getAllKeys();
  const dayKeys = keys.filter((key) => key.startsWith(DAY_KEY_PREFIX));
  const detailKeys = keys.filter((key) => key.startsWith(DETAIL_KEY_PREFIX));

  const toRemove: string[] = [];

  dayKeys.forEach((key) => {
    const dateStr = key.slice(DAY_KEY_PREFIX.length);
    const parsed = new Date(dateStr);
    if (Number.isNaN(parsed.getTime())) {
      toRemove.push(key);
    }
  });

  if (detailKeys.length > 0) {
    const pairs = await multiGet(detailKeys);
    pairs.forEach(([key, raw]) => {
      if (!key || !raw) {
        return;
      }
      try {
        const parsed = JSON.parse(raw) as CachedDetail;
        const cachedAt = new Date(parsed.cached_at);
        if (Number.isNaN(cachedAt.getTime())) {
          toRemove.push(key);
        }
      } catch {
        toRemove.push(key);
      }
    });
  }

  if (toRemove.length > 0) {
    await multiRemove(toRemove);
  }
}

export async function getCachedArticlesByDate(dateStr: string) {
  const key = dayKey(dateStr);
  const raw = await getItem(key);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as CachedDay;
    return parsed.articles;
  } catch {
    await removeItem(key);
    return null;
  }
}

export async function setCachedArticlesByDate(dateStr: string, articles: Article[]) {
  const payload: CachedDay = {
    date: dateStr,
    cached_at: Date.now(),
    articles,
  };
  await setItem(dayKey(dateStr), JSON.stringify(payload));
}

export async function getCachedArticleDetail(id: number) {
  const key = detailKey(id);
  const raw = await getItem(key);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as CachedDetail;
    return parsed.detail;
  } catch {
    await removeItem(key);
    return null;
  }
}

export async function setCachedArticleDetail(detail: ArticleDetail) {
  if (!detail?.id) {
    return;
  }
  const payload: CachedDetail = {
    cached_at: Date.now(),
    published_on: detail.published_on,
    detail,
  };
  await setItem(detailKey(detail.id), JSON.stringify(payload));
}

export async function clearAllArticleCache() {
  const keys = await getAllKeys();
  const articleKeys = keys.filter(
    (key) => key.startsWith(DAY_KEY_PREFIX) || key.startsWith(DETAIL_KEY_PREFIX)
  );
  if (articleKeys.length > 0) {
    await multiRemove(articleKeys);
  }
}
