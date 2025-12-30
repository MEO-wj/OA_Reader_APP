
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { SafeAreaView } from 'react-native-safe-area-context'

import { useRouter } from 'expo-router';
import { Bell, CaretLeft, CaretRight, Funnel } from 'phosphor-react-native';

import { ArticleDetailSheet } from '@/components/article-detail-sheet';
import { ArticleCard } from '@/components/article-card';
import { AmbientBackground } from '@/components/ambient-background';
import { BottomDock } from '@/components/bottom-dock';
import { HomeEmptyState } from '@/components/home-empty-state';
import { HomeLoadingState } from '@/components/home-loading-state';
import { TopBar } from '@/components/top-bar';

import { colors } from '@/constants/palette';
import { useArticles } from '@/hooks/use-articles';
import { useAuthToken } from '@/hooks/use-auth-token';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { usePalette } from '@/hooks/use-palette';
import {
  fetchArticlesCount,
  fetchArticlesPage,
  fetchArticlesPageById,
  fetchTodayArticles,
} from '@/services/articles';
import { getItem, setItem } from '@/storage/universal-storage';
import { formatDateLabel } from '@/utils/date';
import { getAttachmentsCount, getPriority } from '@/utils/article';

import type { Article } from '@/types/article';

export default function HomeScreen() {
  const router = useRouter();
  const [isScrolled, setIsScrolled] = useState(false);
  const colorScheme = useColorScheme() ?? 'light';
  const palette = usePalette();
  const filterStyles = useMemo(
    () => createFilterStyles(palette, colorScheme),
    [colorScheme, palette]
  );

  const fadeIn = useRef(new Animated.Value(0)).current;

  const pageTitle = '今日要闻';
  const currentDate = useMemo(() => formatDateLabel(), []);

  const token = useAuthToken();
  const [filterVisible, setFilterVisible] = useState(false);
  const [selectedUnit, setSelectedUnit] = useState<string | null>(null);
  const [unitExpanded, setUnitExpanded] = useState(false);
  const defaultDateRef = useRef(getTodayDateKey());
  const [selectedDate, setSelectedDate] = useState<string | null>(() => defaultDateRef.current);
  const [selectedDateEnd, setSelectedDateEnd] = useState<string | null>(null);
  const [filterSourceArticles, setFilterSourceArticles] = useState<Article[]>([]);
  const [filterRemoteArticles, setFilterRemoteArticles] = useState<Article[] | null>(null);
  const [filterResultLoading, setFilterResultLoading] = useState(false);
  const filterRequestIdRef = useRef(0);
  const filterDateCacheRef = useRef<Map<string, Article[]>>(new Map());
  const filterDateCompleteRef = useRef<Set<string>>(new Set());
  const [filterDateCacheVersion, setFilterDateCacheVersion] = useState(0);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const totalCountRef = useRef<number | null>(null);
  const totalCountLoadingRef = useRef(false);
  const totalCountRequestRef = useRef(0);
  const [filterLoading, setFilterLoading] = useState(false);
  const [filterLoadComplete, setFilterLoadComplete] = useState(false);
  const filterLoadCompleteRef = useRef(false);
  const filterLoadingRef = useRef(false);
  const filterBootstrappedRef = useRef(false);
  const filterAbortRef = useRef(false);
  const filterArticleMapRef = useRef<Map<number, Article>>(new Map());
  const filterCursorSeenRef = useRef<Set<string>>(new Set());
  const filterPaginationRef = useRef({
    nextBeforeDate: null as string | null,
    nextBeforeId: null as number | null,
    hasMore: false,
  });
  const {
    articles,
    isLoading,
    isRefreshing,
    isLoadingMore,
    activeArticle,
    activeDetail,
    sheetVisible,
    readIds,
    loadArticles,
    loadMoreArticles,
    refreshArticles,
    openArticle,
    closeArticle,
    markAllRead,
    hasUnread,
  } = useArticles(token);

  const filterBaseArticles = useMemo(
    () => (filterSourceArticles.length > 0 ? filterSourceArticles : articles),
    [articles, filterSourceArticles]
  );

  const TOTAL_COUNT_CACHE_KEY = 'articles:total_count';

  const sortedUnits = useMemo(() => sortUnitsByPinyin(STATIC_UNITS), []);
  const unitsWithoutSelected = useMemo(
    () => (selectedUnit ? sortedUnits.filter((unit) => unit !== selectedUnit) : sortedUnits),
    [selectedUnit, sortedUnits]
  );
  const visibleUnits = useMemo(() => {
    if (unitExpanded) {
      return unitsWithoutSelected;
    }
    return unitsWithoutSelected.slice(0, UNIT_COLLAPSE_COUNT);
  }, [unitExpanded, unitsWithoutSelected]);
  const canToggleUnits = sortedUnits.length > UNIT_COLLAPSE_COUNT;

  const calendarRangeEnd = defaultDateRef.current;
  const calendarRangeStart = useMemo(
    () => shiftDateKey(calendarRangeEnd, -365),
    [calendarRangeEnd]
  );
  const minMonthKey = getMonthKey(calendarRangeStart);
  const maxMonthKey = getMonthKey(calendarRangeEnd);
  const [calendarMonth, setCalendarMonth] = useState(() => maxMonthKey);
  const calendarTouchedRef = useRef(false);

  useEffect(() => {
    const focusDate = selectedDateEnd ?? selectedDate;
    if (focusDate) {
      calendarTouchedRef.current = true;
      setCalendarMonth(getMonthKey(focusDate));
      return;
    }
    if (!calendarTouchedRef.current) {
      setCalendarMonth(maxMonthKey);
    }
  }, [maxMonthKey, selectedDate, selectedDateEnd]);

  const calendarCells = useMemo(
    () => buildCalendarCells(calendarMonth, calendarRangeStart, calendarRangeEnd),
    [calendarMonth, calendarRangeEnd, calendarRangeStart]
  );
  const canGoPrevMonth = calendarMonth > minMonthKey;
  const canGoNextMonth = calendarMonth < maxMonthKey;

  const selectedRange = useMemo(
    () => resolveDateRange(selectedDate, selectedDateEnd),
    [selectedDate, selectedDateEnd]
  );
  const filterActive =
    selectedUnit !== null ||
    (selectedRange !== null &&
      (selectedRange.start !== defaultDateRef.current ||
        selectedRange.end !== defaultDateRef.current));
  const isDefaultRange =
    selectedRange !== null &&
    selectedRange.start === defaultDateRef.current &&
    selectedRange.end === defaultDateRef.current;
  const enableFilterPrefetch = false;

  useEffect(() => {
    filterRequestIdRef.current += 1;
    setFilterRemoteArticles(null);
    setFilterResultLoading(false);
  }, [selectedDate, selectedDateEnd, selectedUnit]);

  useEffect(() => {
    totalCountRef.current = totalCount;
  }, [totalCount]);

  useEffect(() => {
    let mounted = true;
    getItem(TOTAL_COUNT_CACHE_KEY)
      .then((value) => {
        if (!mounted || value === null) {
          return;
        }
        const parsed = Number.parseInt(value, 10);
        if (!Number.isNaN(parsed)) {
          setTotalCount(parsed);
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, []);

  const loadTotalCount = useCallback(
    async (force = false) => {
      if (totalCountLoadingRef.current) {
        return;
      }
      if (!force && totalCountRef.current !== null) {
        return;
      }
      totalCountLoadingRef.current = true;
      const requestId = totalCountRequestRef.current + 1;
      totalCountRequestRef.current = requestId;
      try {
        const count = await fetchArticlesCount(token);
        if (totalCountRequestRef.current === requestId && typeof count === 'number') {
          setTotalCount(count);
          void setItem(TOTAL_COUNT_CACHE_KEY, String(count));
        }
      } catch {
        // 获取失败时保留上一次的总数，避免闪回到占位符
      } finally {
        if (totalCountRequestRef.current === requestId) {
          totalCountLoadingRef.current = false;
        }
      }
    },
    [token]
  );

  useEffect(() => {
    void loadTotalCount(true);
  }, [loadTotalCount, token]);

  useEffect(() => {
    if (filterVisible && totalCountRef.current === null) {
      void loadTotalCount(true);
    }
  }, [filterVisible, loadTotalCount]);

  const filteredArticles = useMemo(() => {
    if (filterActive && filterRemoteArticles !== null) {
      return filterRemoteArticles;
    }
    const source = filterActive ? filterBaseArticles : articles;
    const activeRange = selectedRange;
    return source.filter((article) => {
      if (selectedUnit) {
        const normalized = normalizeUnit(article.unit);
        if (normalized !== selectedUnit) {
          return false;
        }
      }
      if (activeRange) {
        const dateKey = getArticleDateKey(article);
        if (!dateKey) {
          return false;
        }
        if (dateKey < activeRange.start || dateKey > activeRange.end) {
          return false;
        }
      }
      return true;
    });
  }, [
    articles,
    filterActive,
    filterBaseArticles,
    filterRemoteArticles,
    selectedRange,
    selectedUnit,
  ]);

  const selectedRangeKeys = useMemo(() => {
    if (!selectedRange) {
      return [] as string[];
    }
    return buildDateRangeKeys(selectedRange.start, selectedRange.end);
  }, [selectedRange]);

  const isSelectedRangeCached = useMemo(() => {
    if (!selectedRange || selectedRangeKeys.length === 0) {
      return false;
    }
    const completed = filterDateCompleteRef.current;
    return selectedRangeKeys.every((key) => completed.has(key));
  }, [selectedRange, selectedRangeKeys, filterDateCacheVersion]);

  const cachedRangeCount = useMemo(() => {
    if (!selectedRange || !isSelectedRangeCached) {
      return null;
    }
    return countArticlesFromDateCache(
      selectedRangeKeys,
      selectedUnit,
      filterDateCacheRef.current
    );
  }, [isSelectedRangeCached, selectedRange, selectedRangeKeys, selectedUnit, filterDateCacheVersion]);

  const filterCountText = useMemo(() => {
    if (cachedRangeCount !== null) {
      return `当前 ${cachedRangeCount}/${totalCount ?? '--'}`;
    }
    if (filterRemoteArticles !== null) {
      return `当前 ${filterRemoteArticles.length}/${totalCount ?? '--'}`;
    }
    if (selectedRange && !isSelectedRangeCached) {
      return `当前 --/${totalCount ?? '--'}`;
    }
    return `当前 ${filteredArticles.length}/${totalCount ?? '--'}`;
  }, [
    cachedRangeCount,
    filterRemoteArticles,
    filteredArticles.length,
    isSelectedRangeCached,
    selectedRange,
    totalCount,
  ]);

  const mergeFilterArticles = useCallback((list: Article[]) => {
    if (list.length === 0) {
      return;
    }
    const map = filterArticleMapRef.current;
    let changed = false;
    list.forEach((article) => {
      if (!article?.id) {
        return;
      }
      if (!map.has(article.id)) {
        map.set(article.id, article);
        changed = true;
      }
    });
    if (changed) {
      setFilterSourceArticles(sortArticlesByDateDesc(Array.from(map.values())));
    }
  }, []);

  useEffect(() => {
    mergeFilterArticles(articles);
  }, [articles, mergeFilterArticles]);

  useEffect(() => {
    if (isLoading) {
      return;
    }
    const todayKey = defaultDateRef.current;
    if (!todayKey) {
      return;
    }
    filterDateCacheRef.current.set(todayKey, sortArticlesByDateDesc(articles));
    filterDateCompleteRef.current.add(todayKey);
    setFilterDateCacheVersion((prev) => prev + 1);
  }, [articles, isLoading]);

  useEffect(() => {
    filterLoadCompleteRef.current = filterLoadComplete;
  }, [filterLoadComplete]);

  const loadAllFilterArticles = useCallback(async (bootstrap = false) => {
    if (filterLoadingRef.current || (!bootstrap && filterLoadCompleteRef.current)) {
      return;
    }
    filterLoadingRef.current = true;
    setFilterLoading(true);
    filterAbortRef.current = false;

    if (bootstrap) {
      setFilterLoadComplete(false);
      filterLoadCompleteRef.current = false;
      filterCursorSeenRef.current.clear();
      const previousMap = new Map(filterArticleMapRef.current);
      try {
        const response = await fetchTodayArticles(token);
        if (!filterAbortRef.current) {
          filterArticleMapRef.current.clear();
          setFilterSourceArticles([]);
          mergeFilterArticles(response.articles);
          filterPaginationRef.current = {
            nextBeforeDate: null,
            nextBeforeId: Number.MAX_SAFE_INTEGER,
            hasMore: true,
          };
        }
      } catch {
        filterArticleMapRef.current = previousMap;
        setFilterSourceArticles(sortArticlesByDateDesc(Array.from(previousMap.values())));
        if (previousMap.size === 0) {
          mergeFilterArticles(articles);
        }
        filterPaginationRef.current = {
          nextBeforeDate: null,
          nextBeforeId: Number.MAX_SAFE_INTEGER,
          hasMore: true,
        };
      }
    }

    const pagination = filterPaginationRef.current;
    const pageLimit = 50;
    const maxPages = 200;
    let pageCount = 0;
    let beforeId = pagination.nextBeforeId ?? Number.MAX_SAFE_INTEGER;
    let hasMoreLocal = pagination.hasMore;

    while (!filterAbortRef.current && hasMoreLocal && beforeId && pageCount < maxPages) {
      try {
        const cursorKey = `v1:${beforeId}`;
        if (filterCursorSeenRef.current.has(cursorKey)) {
          hasMoreLocal = false;
          break;
        }
        filterCursorSeenRef.current.add(cursorKey);
        const response = await fetchArticlesPageById(beforeId, token, pageLimit);

        if (response.articles.length === 0) {
          hasMoreLocal = false;
          break;
        }

        mergeFilterArticles(response.articles);
        const oldestId = response.articles.reduce((minId, article) => {
          if (article?.id && article.id < minId) {
            return article.id;
          }
          return minId;
        }, response.articles[0].id);
        let nextId = response.next_before_id ?? oldestId;
        if (!nextId || nextId >= beforeId) {
          nextId = oldestId;
        }
        if (!nextId || nextId >= beforeId) {
          hasMoreLocal = false;
          break;
        }
        beforeId = nextId;
        hasMoreLocal = response.has_more || response.articles.length >= pageLimit;
        filterPaginationRef.current = {
          nextBeforeDate: null,
          nextBeforeId: beforeId,
          hasMore: hasMoreLocal,
        };
        pageCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 0));
      } catch {
        break;
      }
    }

    if (!filterAbortRef.current) {
      const done = !hasMoreLocal || pageCount >= maxPages;
      setFilterLoadComplete(done);
      filterLoadCompleteRef.current = done;
    }
    setFilterLoading(false);
    filterLoadingRef.current = false;
  }, [articles, mergeFilterArticles, token]);

  const loadFilteredArticles = useCallback(async () => {
    const range = resolveDateRange(selectedDate, selectedDateEnd);
    if (!range) {
      setFilterRemoteArticles(null);
      return;
    }
    const rangeKeys = buildDateRangeKeys(range.start, range.end);
    const missingSpans = getMissingDateSpans(rangeKeys, filterDateCompleteRef.current);
    if (missingSpans.length === 0) {
      const cachedList = buildArticlesFromDateCache(
        rangeKeys,
        selectedUnit,
        filterDateCacheRef.current
      );
      setFilterRemoteArticles(cachedList);
      setFilterResultLoading(false);
      return;
    }
    const requestId = filterRequestIdRef.current + 1;
    filterRequestIdRef.current = requestId;
    setFilterResultLoading(true);
    setFilterRemoteArticles(null);
    const pageLimit = 50;
    const maxPages = 200;
    let cacheTouched = false;

    try {
      for (const span of missingSpans) {
        let beforeDate = span.end;
        let beforeId = Number.MAX_SAFE_INTEGER;
        let hasMoreLocal = true;
        let pageCount = 0;
        let spanFullyCovered = false;
        const cursorSeen = new Set<string>();
        const spanKeys = buildDateRangeKeys(span.start, span.end);
        const spanBuckets = new Map<string, Map<number, Article>>();

        while (hasMoreLocal && pageCount < maxPages) {
          const cursorKey = `${beforeDate}:${beforeId}`;
          if (cursorSeen.has(cursorKey)) {
            break;
          }
          cursorSeen.add(cursorKey);
          const response = await fetchArticlesPage(beforeDate, beforeId, token, pageLimit);
          if (filterRequestIdRef.current !== requestId) {
            return;
          }
          if (response.articles.length === 0) {
            spanFullyCovered = !response.has_more;
            break;
          }
          response.articles.forEach((article) => {
            const dateKey = getArticleDateKey(article);
            if (!dateKey || dateKey < span.start || dateKey > span.end) {
              return;
            }
            if (!article?.id) {
              return;
            }
            const bucket = spanBuckets.get(dateKey) ?? new Map<number, Article>();
            bucket.set(article.id, article);
            spanBuckets.set(dateKey, bucket);
          });

          const nextDate = response.next_before_date;
          const nextId = response.next_before_id;
          if (!nextDate || !nextId) {
            spanFullyCovered = true;
            break;
          }
          if (nextDate < span.start) {
            spanFullyCovered = true;
            break;
          }
          if (nextDate === beforeDate && nextId === beforeId) {
            break;
          }
          beforeDate = nextDate;
          beforeId = nextId;
          hasMoreLocal = response.has_more;
          if (!hasMoreLocal) {
            spanFullyCovered = true;
            break;
          }
          pageCount += 1;
          await new Promise((resolve) => setTimeout(resolve, 0));
        }

        if (filterRequestIdRef.current !== requestId) {
          return;
        }

        const oldestFetchedDate = getOldestDateKey(spanBuckets);
        if (spanFullyCovered && oldestFetchedDate && oldestFetchedDate > span.start) {
          spanFullyCovered = false;
        }

        const cacheMap = filterDateCacheRef.current;
        if (spanFullyCovered) {
          spanKeys.forEach((dateKey) => {
            const bucket = spanBuckets.get(dateKey);
            const list = bucket ? Array.from(bucket.values()) : [];
            cacheMap.set(dateKey, sortArticlesByDateDesc(list));
            filterDateCompleteRef.current.add(dateKey);
          });
        } else {
          spanBuckets.forEach((bucket, dateKey) => {
            const list = Array.from(bucket.values());
            cacheMap.set(dateKey, sortArticlesByDateDesc(list));
            filterDateCompleteRef.current.add(dateKey);
          });
        }
        cacheTouched = true;
      }
    } catch {
      // 保持已有数据
    } finally {
      if (filterRequestIdRef.current === requestId) {
        if (cacheTouched) {
          setFilterDateCacheVersion((prev) => prev + 1);
        }
        const nextList = buildArticlesFromDateCache(
          rangeKeys,
          selectedUnit,
          filterDateCacheRef.current
        );
        setFilterRemoteArticles(nextList);
        setFilterResultLoading(false);
      }
    }
  }, [selectedDate, selectedDateEnd, selectedUnit, token]);

  const handleDateSelect = useCallback(
    (dateKey: string) => {
      calendarTouchedRef.current = true;
      if (!selectedDate || (selectedDate && selectedDateEnd)) {
        setSelectedDate(dateKey);
        setSelectedDateEnd(null);
        return;
      }
      if (!selectedDateEnd) {
        if (dateKey < selectedDate) {
          setSelectedDateEnd(selectedDate);
          setSelectedDate(dateKey);
          return;
        }
        setSelectedDateEnd(dateKey);
      }
    },
    [selectedDate, selectedDateEnd]
  );

  useEffect(() => {
    if (!filterVisible) {
      filterAbortRef.current = true;
      filterLoadingRef.current = false;
      setFilterLoading(false);
      filterBootstrappedRef.current = false;
      return;
    }
    if (selectedDate === null) {
      setSelectedDate(defaultDateRef.current);
    }
    if (selectedDateEnd === null && selectedDate === null) {
      setSelectedDateEnd(defaultDateRef.current);
    }
    if (!filterBootstrappedRef.current && enableFilterPrefetch) {
      filterBootstrappedRef.current = true;
      void loadAllFilterArticles(true);
    }
  }, [enableFilterPrefetch, filterVisible, loadAllFilterArticles, selectedDate, selectedDateEnd]);

  const loadArticlesWithFade = useCallback(async () => {
    await loadArticles();
    Animated.timing(fadeIn, {
      toValue: 1,
      duration: 500,
      useNativeDriver: true,
    }).start();
  }, [fadeIn, loadArticles]);

  const applyFilterAndClose = useCallback(() => {
    setFilterVisible(false);
    if (!filterActive) {
      setFilterRemoteArticles(null);
      return;
    }
    void loadFilteredArticles();
  }, [filterActive, loadFilteredArticles]);

  useEffect(() => {
    loadArticlesWithFade();
  }, [loadArticlesWithFade]);

  const renderItem = useCallback(
    ({ item, index }: { item: Article; index: number }) => {
      const attachmentsCount = getAttachmentsCount(item.attachments);
      const priority = getPriority(item.title);
      const isRead = !!readIds[item.id];
      return (
        <ArticleCard
          article={item}
          index={index}
          isRead={isRead}
          attachmentsCount={attachmentsCount}
          priority={priority}
          onPress={openArticle}
        />
      );
    },
    [openArticle, readIds]
  );

  // 保留刷新能力，首页不做无限加载（仅展示当日信息）
  const renderFooter = useCallback(() => {
    if (!isLoadingMore) {
      return null;
    }
    return (
      <View style={styles.loadingFooter}>
        <ActivityIndicator size="small" color={colors.gold500} />
      </View>
    );
  }, [isLoadingMore]);

  const isFilterFetching = filterResultLoading && filterActive;

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle={colorScheme === 'dark' ? 'light-content' : 'dark-content'} />
      <AmbientBackground variant="home" />
      <TopBar
        variant="explore"
        title={pageTitle}
        dateText={currentDate}
        isScrolled={isScrolled}
        hasUnread={hasUnread}
        onPressAction={markAllRead}
        actions={(
          <View style={filterStyles.actionRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="筛选通知"
              onPress={() => setFilterVisible(true)}
              style={({ pressed }) => [
                filterStyles.actionButton,
                pressed && filterStyles.actionButtonPressed,
              ]}
            >
              <Funnel size={18} color={palette.stone400} weight="bold" />
              {filterActive && <View style={filterStyles.filterDot} />}
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="标记全部已读"
              onPress={markAllRead}
              style={({ pressed }) => [
                filterStyles.actionButton,
                pressed && filterStyles.actionButtonPressed,
              ]}
            >
              <Bell size={18} color={palette.stone400} weight="fill" />
              {hasUnread && <View style={filterStyles.bellDot} />}
            </Pressable>
          </View>
        )}
      />

      <Animated.View style={[styles.listWrap, { opacity: fadeIn }]}>
        {isLoading || isFilterFetching ? (
          <HomeLoadingState />
        ) : (
          <FlatList
            data={filteredArticles}
            keyExtractor={(item) => item.id.toString()}
            renderItem={renderItem}
            contentContainerStyle={styles.listContent}
            showsVerticalScrollIndicator={false}
            onScroll={(event) => setIsScrolled(event.nativeEvent.contentOffset.y > 20)}
            scrollEventThrottle={16}
            refreshControl={
              <RefreshControl
                refreshing={isRefreshing}
                onRefresh={refreshArticles}
                tintColor={colors.gold500}
              />
            }
            onEndReached={undefined}
            ListEmptyComponent={<HomeEmptyState />}
            ListFooterComponent={null}
          />
        )}
      </Animated.View>

      <BottomDock
        activeTab="home"
        onHome={() => undefined}
        onAi={() => router.push('/(tabs)/explore')}
        onSettings={() => router.push('/(tabs)/settings')}
      />

      <ArticleDetailSheet
        visible={sheetVisible}
        article={activeArticle}
        detail={activeDetail}
        onClose={closeArticle}
      />

      <Modal
        transparent
        visible={filterVisible}
        animationType="fade"
        onRequestClose={applyFilterAndClose}
      >
        <View style={filterStyles.filterOverlay}>
          <Pressable style={filterStyles.filterBackdrop} onPress={applyFilterAndClose} />
          <View style={filterStyles.filterCard}>
            <View style={filterStyles.filterHeader}>
              <View>
                <Text style={filterStyles.filterTitle}>{'筛选通知'}</Text>
                <Text style={filterStyles.filterSub}>{filterCountText}</Text>
              </View>
              {filterActive && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="清除筛选"
                  onPress={() => {
                    setSelectedUnit(null);
                    setSelectedDate(defaultDateRef.current);
                    setSelectedDateEnd(null);
                    setFilterRemoteArticles(null);
                  }}
                  style={({ pressed }) => [
                    filterStyles.clearButton,
                    pressed && filterStyles.clearButtonPressed,
                  ]}
                >
                  <Text style={filterStyles.clearButtonText}>{'清除'}</Text>
                </Pressable>
              )}
            </View>
            <ScrollView
              style={filterStyles.filterBody}
              contentContainerStyle={filterStyles.filterBodyContent}
              showsVerticalScrollIndicator={false}
            >
              <View style={filterStyles.section}>
                <View style={filterStyles.sectionHeaderRow}>
                  <Text style={filterStyles.sectionTitle}>{'发布单位'}</Text>
                  {canToggleUnits && (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={unitExpanded ? '收起单位' : '展开单位'}
                      onPress={() => setUnitExpanded((prev) => !prev)}
                      style={({ pressed }) => [
                        filterStyles.sectionAction,
                        pressed && filterStyles.sectionActionPressed,
                      ]}
                    >
                      <Text style={filterStyles.sectionActionText}>
                        {unitExpanded ? '收起' : '展开'}
                      </Text>
                    </Pressable>
                  )}
                </View>
                <View style={filterStyles.chipGroup}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="全部发布单位"
                    onPress={() => setSelectedUnit(null)}
                    style={({ pressed }) => [
                      filterStyles.chip,
                      selectedUnit === null && filterStyles.chipSelected,
                      pressed && filterStyles.chipPressed,
                    ]}
                  >
                    <Text
                      style={[
                        filterStyles.chipText,
                        selectedUnit === null && filterStyles.chipTextSelected,
                      ]}
                    >
                      全部
                    </Text>
                  </Pressable>
                  {selectedUnit && (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={`已选择${selectedUnit}`}
                      onPress={() => setSelectedUnit(selectedUnit)}
                      style={({ pressed }) => [
                        filterStyles.chip,
                        filterStyles.chipSelected,
                        pressed && filterStyles.chipPressed,
                      ]}
                    >
                      <Text style={[filterStyles.chipText, filterStyles.chipTextSelected]}>
                        {selectedUnit}
                      </Text>
                    </Pressable>
                  )}
                  {visibleUnits.map((unit) => (
                    <Pressable
                      key={unit}
                      accessibilityRole="button"
                      accessibilityLabel={`选择${unit}`}
                      onPress={() => setSelectedUnit(unit)}
                      style={({ pressed }) => [
                        filterStyles.chip,
                        selectedUnit === unit && filterStyles.chipSelected,
                        pressed && filterStyles.chipPressed,
                      ]}
                    >
                      <Text
                        style={[
                          filterStyles.chipText,
                          selectedUnit === unit && filterStyles.chipTextSelected,
                        ]}
                      >
                        {unit}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              <View style={filterStyles.section}>
                <Text style={filterStyles.sectionTitle}>{'发布日期'}</Text>
                <View style={filterStyles.dateToolbar}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="今天"
                    onPress={() => {
                      setSelectedDate(defaultDateRef.current);
                      setSelectedDateEnd(null);
                    }}
                    style={({ pressed }) => [
                      filterStyles.chip,
                      isDefaultRange && filterStyles.chipSelected,
                      pressed && filterStyles.chipPressed,
                    ]}
                  >
                    <Text
                      style={[
                        filterStyles.chipText,
                        isDefaultRange && filterStyles.chipTextSelected,
                      ]}
                    >
                      今天
                    </Text>
                  </Pressable>
                  {selectedRange && (
                    <Text style={filterStyles.dateHint}>
                      已选{formatDateRangeOption(selectedRange)}
                    </Text>
                  )}
                </View>

                <Text style={filterStyles.dateGuide}>先选开始日期，再选结束日期</Text>

                <View style={filterStyles.calendarWrap}>
                    <View style={filterStyles.calendarHeader}>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="上一个月"
                        onPress={() => {
                          if (!canGoPrevMonth) {
                            return;
                          }
                          calendarTouchedRef.current = true;
                          setCalendarMonth(shiftMonth(calendarMonth, -1));
                        }}
                        style={({ pressed }) => [
                          filterStyles.calendarNavButton,
                          !canGoPrevMonth && filterStyles.calendarNavDisabled,
                          pressed && canGoPrevMonth && filterStyles.calendarNavPressed,
                        ]}
                      >
                        <CaretLeft
                          size={16}
                          color={canGoPrevMonth ? palette.stone600 : palette.stone300}
                          weight="bold"
                        />
                      </Pressable>
                      <Text style={filterStyles.calendarMonthText}>
                        {formatMonthLabel(calendarMonth)}
                      </Text>
                      <Pressable
                        accessibilityRole="button"
                        accessibilityLabel="下一个月"
                        onPress={() => {
                          if (!canGoNextMonth) {
                            return;
                          }
                          calendarTouchedRef.current = true;
                          setCalendarMonth(shiftMonth(calendarMonth, 1));
                        }}
                        style={({ pressed }) => [
                          filterStyles.calendarNavButton,
                          !canGoNextMonth && filterStyles.calendarNavDisabled,
                          pressed && canGoNextMonth && filterStyles.calendarNavPressed,
                        ]}
                      >
                        <CaretRight
                          size={16}
                          color={canGoNextMonth ? palette.stone600 : palette.stone300}
                          weight="bold"
                        />
                      </Pressable>
                    </View>

                    <View style={filterStyles.calendarWeekRow}>
                      {['一', '二', '三', '四', '五', '六', '日'].map((label) => (
                        <Text key={label} style={filterStyles.calendarWeekText}>
                          {label}
                        </Text>
                      ))}
                    </View>

                    <View style={filterStyles.calendarGrid}>
                      {calendarCells.map((cell, index) => {
                        if (!cell) {
                          return <View key={`blank-${index}`} style={filterStyles.calendarCell} />;
                        }
                        const range = selectedRange;
                        const inRange = range
                          ? cell.dateKey >= range.start && cell.dateKey <= range.end
                          : false;
                        const isRangeStart = range ? cell.dateKey === range.start : false;
                        const isRangeEnd = range ? cell.dateKey === range.end : false;
                        const isSelected = isRangeStart || isRangeEnd;
                        return (
                          <Pressable
                            key={cell.dateKey}
                            accessibilityRole="button"
                            accessibilityLabel={`选择${cell.dateKey}`}
                            disabled={!cell.enabled}
                            onPress={() => handleDateSelect(cell.dateKey)}
                            style={({ pressed }) => [
                              filterStyles.calendarCell,
                              inRange && filterStyles.calendarCellInRange,
                              isSelected && filterStyles.calendarCellSelected,
                              !cell.enabled && filterStyles.calendarCellDisabled,
                              pressed && cell.enabled && filterStyles.calendarCellPressed,
                            ]}
                          >
                            <Text
                              style={[
                                filterStyles.calendarCellText,
                                inRange && filterStyles.calendarCellTextInRange,
                                isSelected && filterStyles.calendarCellTextSelected,
                                !cell.enabled && filterStyles.calendarCellTextDisabled,
                              ]}
                            >
                              {cell.day}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </View>
              </View>

              {filterLoading && (
                <View style={filterStyles.loadingRow}>
                  <ActivityIndicator size="small" color={palette.gold500} />
                  <Text style={filterStyles.loadingText}>正在加载更多筛选项...</Text>
                </View>
              )}
              {!filterLoading && filterLoadComplete && filterBaseArticles.length === 0 && (
                <Text style={filterStyles.emptyHint}>暂无可筛选的文章</Text>
              )}
            </ScrollView>

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="完成筛选"
              onPress={applyFilterAndClose}
              style={({ pressed }) => [
                filterStyles.confirmButton,
                pressed && filterStyles.confirmButtonPressed,
              ]}
            >
              <Text style={filterStyles.confirmButtonText}>{'完成'}</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  listWrap: {
    flex: 1,
    paddingTop: 24,
  },
  listContent: {
    paddingHorizontal: 20,
    paddingBottom: 130,
  },
  loadingFooter: {
    paddingVertical: 16,
    alignItems: 'center',
  },
});

function normalizeUnit(unit?: string) {
  const trimmed = unit?.trim();
  return trimmed ? trimmed : null;
}

function getArticleDateKey(article: Article) {
  const raw = article.published_on || article.created_at;
  if (!raw) {
    return null;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
    return raw.slice(0, 10);
  }
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatDateOption(dateKey: string) {
  return dateKey.replace(/-/g, '/');
}

function resolveDateRange(start: string | null, end: string | null) {
  if (!start && !end) {
    return null;
  }
  const startKey = start ?? end!;
  const endKey = end ?? startKey;
  if (startKey <= endKey) {
    return { start: startKey, end: endKey };
  }
  return { start: endKey, end: startKey };
}

function formatDateRangeOption(range: { start: string; end: string }) {
  if (range.start === range.end) {
    return formatDateOption(range.start);
  }
  return `${formatDateOption(range.start)} - ${formatDateOption(range.end)}`;
}

type CalendarCell = {
  day: number;
  dateKey: string;
  enabled: boolean;
};

function getTodayDateKey() {
  return new Date().toISOString().slice(0, 10);
}

function shiftDateKey(dateKey: string, offsetDays: number) {
  const base = new Date(`${dateKey}T00:00:00Z`);
  base.setDate(base.getDate() + offsetDays);
  return base.toISOString().slice(0, 10);
}

function getMonthKey(dateKey: string) {
  return dateKey.slice(0, 7);
}

function shiftMonth(monthKey: string, offset: number) {
  const [yearText, monthText] = monthKey.split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  if (!year || !month) {
    return monthKey;
  }
  const next = new Date(year, month - 1 + offset, 1);
  const nextYear = next.getFullYear();
  const nextMonth = `${next.getMonth() + 1}`.padStart(2, '0');
  return `${nextYear}-${nextMonth}`;
}

function buildCalendarCells(monthKey: string, rangeStart: string, rangeEnd: string) {
  const [yearText, monthText] = monthKey.split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  if (!year || !month) {
    return [] as Array<CalendarCell | null>;
  }
  const firstDay = new Date(year, month - 1, 1);
  const startWeekday = (firstDay.getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells: Array<CalendarCell | null> = [];
  for (let i = 0; i < startWeekday; i += 1) {
    cells.push(null);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateKey = `${year}-${`${month}`.padStart(2, '0')}-${`${day}`.padStart(2, '0')}`;
    const enabled = dateKey >= rangeStart && dateKey <= rangeEnd;
    cells.push({
      day,
      dateKey,
      enabled,
    });
  }
  return cells;
}

function formatMonthLabel(monthKey: string) {
  const [yearText, monthText] = monthKey.split('-');
  const year = Number(yearText);
  const month = Number(monthText);
  if (!year || !month) {
    return monthKey;
  }
  return `${year}年${month}月`;
}

function getArticleSortTime(article: Article) {
  const raw = article.created_at || article.published_on;
  if (!raw) {
    return 0;
  }
  const timestamp = Date.parse(raw);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sortArticlesByDateDesc(list: Article[]) {
  return list.slice().sort((a, b) => getArticleSortTime(b) - getArticleSortTime(a));
}

function buildDateRangeKeys(start: string, end: string) {
  if (!start || !end || start > end) {
    return [] as string[];
  }
  const keys: string[] = [];
  let cursor = start;
  while (cursor <= end) {
    keys.push(cursor);
    cursor = shiftDateKey(cursor, 1);
    if (keys.length > 370) {
      break;
    }
  }
  return keys;
}

function getMissingDateSpans(rangeKeys: string[], completed: Set<string>) {
  const spans: Array<{ start: string; end: string }> = [];
  let spanStart: string | null = null;
  let spanEnd: string | null = null;
  rangeKeys.forEach((dateKey) => {
    if (!completed.has(dateKey)) {
      if (!spanStart) {
        spanStart = dateKey;
      }
      spanEnd = dateKey;
      return;
    }
    if (spanStart && spanEnd) {
      spans.push({ start: spanStart, end: spanEnd });
      spanStart = null;
      spanEnd = null;
    }
  });
  if (spanStart && spanEnd) {
    spans.push({ start: spanStart, end: spanEnd });
  }
  return spans;
}

function buildArticlesFromDateCache(
  rangeKeys: string[],
  unit: string | null,
  cache: Map<string, Article[]>
) {
  const list: Article[] = [];
  const seen = new Set<number>();
  rangeKeys.forEach((dateKey) => {
    const bucket = cache.get(dateKey) ?? [];
    bucket.forEach((article) => {
      if (!article?.id) {
        return;
      }
      if (unit) {
        const normalized = normalizeUnit(article.unit);
        if (normalized !== unit) {
          return;
        }
      }
      if (seen.has(article.id)) {
        return;
      }
      seen.add(article.id);
      list.push(article);
    });
  });
  return sortArticlesByDateDesc(list);
}

function getOldestDateKey(spanBuckets: Map<string, Map<number, Article>>) {
  let oldest: string | null = null;
  spanBuckets.forEach((_bucket, dateKey) => {
    if (!oldest || dateKey < oldest) {
      oldest = dateKey;
    }
  });
  return oldest;
}

function countArticlesFromDateCache(
  rangeKeys: string[],
  unit: string | null,
  cache: Map<string, Article[]>
) {
  const seen = new Set<number>();
  let count = 0;
  rangeKeys.forEach((dateKey) => {
    const bucket = cache.get(dateKey) ?? [];
    bucket.forEach((article) => {
      if (!article?.id) {
        return;
      }
      if (unit) {
        const normalized = normalizeUnit(article.unit);
        if (normalized !== unit) {
          return;
        }
      }
      if (seen.has(article.id)) {
        return;
      }
      seen.add(article.id);
      count += 1;
    });
  });
  return count;
}

const UNIT_COLLAPSE_COUNT = 18;

function sortUnitsByPinyin(list: string[]) {
  try {
    const collator = new Intl.Collator('zh-Hans-u-co-pinyin', { sensitivity: 'base' });
    return list.slice().sort((a, b) => collator.compare(a, b));
  } catch {
    return list.slice().sort((a, b) => a.localeCompare(b, 'zh-CN'));
  }
}

const STATIC_UNITS = Array.from(
  new Set([
    '汕头大学',
    '汕头大学党委',
    '党委组织部',
    '党委宣传统战部',
    '机关党委',
    '党政办公室',
    '监察审计处',
    '资源管理处',
    '发展规划处',
    '人事处',
    '财务处',
    '教务处',
    '科研处',
    '基建处',
    '本科生院',
    '书院总院',
    '工会',
    '研究生院',
    '学生处',
    '校团委',
    '招生就业办公室',
    '创新创业研究院',
    '网络与信息中心',
    '创业学院',
    '党委工作部综合办公室',
    '党委工作部',
    '本科生院综合办公室',
    '党委工作部宣传办公室',
    '行政事务部综合办公室',
    '行政事务部发展规划办公室',
    '行政事务部人力资源中心',
    '行政事务部财务管理服务中心',
    '行政事务部国际交流服务中心',
    '行政事务部资源管理服务中心',
    '行政事务部招投标中心',
    '行政事务部',
    '学生培养中心',
    '汕头大学纪委',
    '校友工作办公室',
    '教务管理服务中心',
    '党委宣传部',
    '研究生学院',
    '纪委办公室',
    '党委组织统战部',
    '图书馆',
    '工学院',
    '法学院',
    '理学院',
    '商学院',
    '马克思主义学院',
    '社科部',
    '体育部',
    '文学院',
    '至诚书院',
    '思源书院',
    '知行书院',
    '弘毅书院',
    '淑德书院',
    '修远书院',
    '敬一书院',
    '明德书院',
    '德馨书院',
    '继续教育学院',
    '长江艺术与设计学院',
    '艺术教育中心',
    '长江新闻与传播学院',
    '教师发展中心',
    '英语语言中心',
    '行政事务部校园安全服务中心',
    '校报编辑部',
    '学位评定委员会',
    '华文文学编辑部',
    '学报编辑部',
    '高等教育研究所',
    '招生办公室',
    '汕头大学体育园',
    '中心实验室',
    '教师发展与教育评估中心',
    '发展规划办',
    '港澳台事务办公室',
    '国际交流合作处',
    '学生创业中心',
    '创文工作领导小组',
    '党委教师工作部',
    '党委研究生工作部',
    '党委学生工作部',
    '纪检监察审计处',
    '国际学院',
    '机关第一党总支',
    '机关第二党总支',
    '保卫处',
    '招生就业处',
    '汕头大学汕头校区综合办公室',
    '招投标中心',
    '机关工委',
    '资产经营管理有限公司',
    '公共卫生学院',
    '数学研究所',
    '人民武装部',
    '纪检监察室',
    '审计处',
    '东海岸校区管理委员会',
    '化学化工学院',
    '数学与计算机学院',
    '行川书院',
    '格致书院',
    '山海书院',
    '高退休工作处',
  ])
);

function createFilterStyles(palette: typeof colors, colorScheme: 'light' | 'dark') {
  const actionBg = colorScheme === 'dark' ? 'rgba(20, 19, 18, 0.9)' : palette.white;
  const actionBorder = colorScheme === 'dark' ? 'rgba(255,255,255,0.08)' : palette.gold100;

  return StyleSheet.create({
    actionRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    actionButton: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: actionBg,
      alignItems: 'center',
      justifyContent: 'center',
      borderWidth: 1,
      borderColor: actionBorder,
    },
    actionButtonPressed: {
      transform: [{ scale: 0.96 }],
    },
    filterDot: {
      position: 'absolute',
      top: 9,
      right: 9,
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: palette.gold400,
      borderWidth: 1,
      borderColor: palette.white,
    },
    bellDot: {
      position: 'absolute',
      top: 9,
      right: 9,
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: palette.imperial500,
      borderWidth: 1,
      borderColor: palette.white,
    },
    filterOverlay: {
      flex: 1,
      paddingHorizontal: 20,
      paddingTop: 80,
    },
    filterBackdrop: {
      ...StyleSheet.absoluteFillObject,
      backgroundColor: 'rgba(28, 25, 23, 0.4)',
    },
    filterCard: {
      backgroundColor: palette.white,
      borderRadius: 24,
      padding: 18,
      borderWidth: 1,
      borderColor: palette.stone100,
      maxHeight: '82%',
    },
    filterHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 14,
    },
    filterTitle: {
      fontSize: 16,
      fontWeight: '800',
      color: palette.stone900,
    },
    filterSub: {
      fontSize: 11,
      color: palette.stone400,
      marginTop: 4,
    },
    filterBody: {
      marginTop: 6,
      marginBottom: 12,
    },
    filterBodyContent: {
      paddingBottom: 8,
      gap: 16,
    },
    clearButton: {
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 999,
      backgroundColor: palette.stone100,
    },
    clearButtonPressed: {
      transform: [{ scale: 0.96 }],
    },
    clearButtonText: {
      fontSize: 11,
      fontWeight: '700',
      color: palette.stone600,
      letterSpacing: 1,
    },
    section: {
      marginBottom: 14,
    },
    sectionTitle: {
      fontSize: 12,
      fontWeight: '700',
      color: palette.stone700,
      marginBottom: 10,
    },
    sectionHeaderRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 10,
    },
    sectionAction: {
      paddingHorizontal: 8,
      paddingVertical: 4,
      borderRadius: 999,
      backgroundColor: palette.stone100,
    },
    sectionActionPressed: {
      transform: [{ scale: 0.96 }],
    },
    sectionActionText: {
      fontSize: 10,
      fontWeight: '700',
      color: palette.stone600,
    },
    dateToolbar: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      marginBottom: 10,
      flexWrap: 'wrap',
    },
    dateHint: {
      fontSize: 11,
      color: palette.stone500,
    },
    dateGuide: {
      fontSize: 11,
      color: palette.stone400,
      marginBottom: 10,
    },
    chipGroup: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    chip: {
      paddingHorizontal: 12,
      paddingVertical: 6,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: palette.stone200,
      backgroundColor: palette.white,
    },
    chipSelected: {
      borderColor: palette.gold400,
      backgroundColor: palette.gold50,
    },
    chipPressed: {
      transform: [{ scale: 0.98 }],
    },
    chipText: {
      fontSize: 11,
      fontWeight: '600',
      color: palette.stone600,
    },
    chipTextSelected: {
      color: palette.gold600,
      fontWeight: '700',
    },
    calendarWrap: {
      padding: 12,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: palette.stone100,
      backgroundColor: palette.white,
    },
    calendarHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 8,
    },
    calendarNavButton: {
      width: 28,
      height: 28,
      borderRadius: 14,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: palette.stone100,
    },
    calendarNavDisabled: {
      opacity: 0.4,
    },
    calendarNavPressed: {
      transform: [{ scale: 0.96 }],
    },
    calendarMonthText: {
      fontSize: 13,
      fontWeight: '700',
      color: palette.stone800,
    },
    calendarWeekRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      marginBottom: 6,
    },
    calendarWeekText: {
      width: '14.28%',
      textAlign: 'center',
      fontSize: 10,
      color: palette.stone400,
      fontWeight: '600',
    },
    calendarGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
    },
    calendarCell: {
      width: '14.28%',
      aspectRatio: 1,
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: 10,
      marginBottom: 4,
    },
    calendarCellInRange: {
      backgroundColor: palette.gold50,
    },
    calendarCellSelected: {
      backgroundColor: palette.gold100,
    },
    calendarCellDisabled: {
      opacity: 0.35,
    },
    calendarCellPressed: {
      transform: [{ scale: 0.96 }],
    },
    calendarCellText: {
      fontSize: 12,
      color: palette.stone700,
      fontWeight: '600',
    },
    calendarCellTextInRange: {
      color: palette.stone700,
    },
    calendarCellTextSelected: {
      color: palette.gold600,
      fontWeight: '700',
    },
    calendarCellTextDisabled: {
      color: palette.stone300,
    },
    loadingRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingVertical: 6,
    },
    loadingText: {
      fontSize: 11,
      color: palette.stone500,
    },
    emptyHint: {
      fontSize: 12,
      color: palette.stone400,
    },
    confirmButton: {
      marginTop: 6,
      paddingVertical: 12,
      borderRadius: 16,
      backgroundColor: palette.stone900,
      alignItems: 'center',
    },
    confirmButtonPressed: {
      transform: [{ scale: 0.98 }],
    },
    confirmButtonText: {
      color: palette.white,
      fontSize: 12,
      fontWeight: '800',
      letterSpacing: 2,
    },
  });
}
