
import { useCallback, useMemo, useState } from 'react';

import type { Article, ArticleDetail } from '@/types/article';
import {
  fetchArticleDetail,
  fetchTodayArticles,
  fetchArticlesPage,
} from '@/services/articles';
import {
  getCachedArticleDetail,
  getCachedArticlesByDate,
  getTodayDateString,
  setCachedArticleDetail,
  setCachedArticlesByDate,
  setPaginationState,
  clearPaginationState,
} from '@/storage/article-storage';

type UseArticlesState = {
  articles: Article[];
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingMore: boolean;
  activeArticle: Article | null;
  activeDetail: ArticleDetail | null;
  sheetVisible: boolean;
  readIds: Record<number, boolean>;
  nextBeforeDate: string | null;
  nextBeforeId: number | null;
  hasMore: boolean;
};

export function useArticles(token?: string | null) {
  const [articles, setArticles] = useState<Article[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [activeArticle, setActiveArticle] = useState<Article | null>(null);
  const [activeDetail, setActiveDetail] = useState<ArticleDetail | null>(null);
  const [sheetVisible, setSheetVisible] = useState(false);
  const [readIds, setReadIds] = useState<Record<number, boolean>>({});
  const [nextBeforeDate, setNextBeforeDate] = useState<string | null>(null);
  const [nextBeforeId, setNextBeforeId] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);

  const prefetchArticleDetails = useCallback(
    async (list: Article[]) => {
      for (const article of list) {
        if (!article?.id) {
          continue;
        }
        const cached = await getCachedArticleDetail(article.id);
        if (cached) {
          continue;
        }
        try {
          const detail = await fetchArticleDetail(article.id, token);
          await setCachedArticleDetail(detail);
        } catch {
          // 预缓存失败不影响主流程
        }
      }
    },
    [token]
  );

  const loadArticles = useCallback(async () => {
    setIsLoading(true);
    try {
      // 使用新的 /today 端点
      const dateStr = getTodayDateString();
      const cached = await getCachedArticlesByDate(dateStr);

      // 先显示缓存（如果有），快速响应
      if (cached) {
        setArticles(cached);
      }

      // 无论是否有缓存，都请求服务器获取最新数据
      const response = await fetchTodayArticles(token);
      setArticles(response.articles);
      setNextBeforeDate(response.next_before_date);
      setNextBeforeId(response.next_before_id);
      setHasMore(response.has_more);

      // 保存分页状态
      await setPaginationState({
        next_before_date: response.next_before_date,
        next_before_id: response.next_before_id,
        has_more: response.has_more,
        updated_at: Date.now(),
      });

      // 缓存文章列表
      await setCachedArticlesByDate(dateStr, response.articles);

      // 预缓存文章详情
      void prefetchArticleDetails(response.articles);
    } catch {
      // 如果请求失败且有缓存，保持缓存显示
      const cached = await getCachedArticlesByDate(getTodayDateString());
      if (cached) {
        setArticles(cached);
      } else {
        setArticles([]);
      }
    } finally {
      setIsLoading(false);
    }
  }, [prefetchArticleDetails, token]);

  const loadMoreArticles = useCallback(async () => {
    if (isLoadingMore || !nextBeforeId || !nextBeforeDate || !hasMore) {
      return;
    }

    setIsLoadingMore(true);
    try {
      const response = await fetchArticlesPage(nextBeforeDate, nextBeforeId, token, 20);

      if (response.articles.length === 0) {
        setNextBeforeDate(null);
        setNextBeforeId(null);
        setHasMore(false);
        await setPaginationState({
          next_before_date: null,
          next_before_id: null,
          has_more: false,
          updated_at: Date.now(),
        });
        return;
      }

      // 追加新文章到现有列表
      setArticles((prev) => [...prev, ...response.articles]);
      setNextBeforeDate(response.next_before_date);
      setNextBeforeId(response.next_before_id);
      setHasMore(response.has_more);

      // 更新分页状态
      await setPaginationState({
        next_before_date: response.next_before_date,
        next_before_id: response.next_before_id,
        has_more: response.has_more,
        updated_at: Date.now(),
      });

      // 预缓存新加载的文章详情
      void prefetchArticleDetails(response.articles);
    } catch {
      // 加载更多失败不影响现有数据
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, nextBeforeId, nextBeforeDate, hasMore, token, prefetchArticleDetails]);

  const refreshArticles = useCallback(async () => {
    setIsRefreshing(true);
    try {
      // 强制从服务器获取，不使用缓存
      const response = await fetchTodayArticles(token);
      setArticles(response.articles);
      setNextBeforeDate(response.next_before_date);
      setNextBeforeId(response.next_before_id);
      setHasMore(response.has_more);

      // 清除旧的分页状态，使用新的
      await clearPaginationState();
      await setPaginationState({
        next_before_date: response.next_before_date,
        next_before_id: response.next_before_id,
        has_more: response.has_more,
        updated_at: Date.now(),
      });

      await setCachedArticlesByDate(getTodayDateString(), response.articles);
      void prefetchArticleDetails(response.articles);
    } catch {
      // 刷新失败时不改变现有数据
    } finally {
      setIsRefreshing(false);
    }
  }, [prefetchArticleDetails, token]);

  const openArticle = useCallback(
    async (article: Article) => {
      setActiveArticle(article);
      setSheetVisible(true);
      setReadIds((prev) => ({ ...prev, [article.id]: true }));
      const cachedDetail = await getCachedArticleDetail(article.id);
      if (cachedDetail) {
        setActiveDetail(cachedDetail);
        return;
      }
      setActiveDetail(null);
      try {
        const detail = await fetchArticleDetail(article.id, token);
        setActiveDetail(detail);
        await setCachedArticleDetail(detail);
      } catch {
        setActiveDetail(null);
      }
    },
    [token]
  );

  const closeArticle = useCallback(() => {
    setSheetVisible(false);
    setActiveArticle(null);
    setActiveDetail(null);
  }, []);

  const markAllRead = useCallback(() => {
    setReadIds((prev) => {
      const next: Record<number, boolean> = { ...prev };
      articles.forEach((article) => {
        next[article.id] = true;
      });
      return next;
    });
  }, [articles]);

  const hasUnread = useMemo(
    () => articles.some((article) => !readIds[article.id]),
    [articles, readIds]
  );

  const state: UseArticlesState = {
    articles,
    isLoading,
    isRefreshing,
    isLoadingMore,
    activeArticle,
    activeDetail,
    sheetVisible,
    readIds,
    nextBeforeDate,
    nextBeforeId,
    hasMore,
  };

  return {
    ...state,
    loadArticles,
    loadMoreArticles,
    refreshArticles,
    openArticle,
    closeArticle,
    markAllRead,
    hasUnread,
    setArticles,
    setReadIds,
  };
}
