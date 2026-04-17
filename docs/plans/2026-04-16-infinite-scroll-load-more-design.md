# 滚动加载更多文章 — 设计

## 问题

首页 FlatList 的 `onEndReached={undefined}` 写死，Hook 层的 `loadMoreArticles()` 从未被调用。

## 现状

- `use-articles.ts` 的 `loadMoreArticles()` 已完整实现：游标分页、追加列表、预缓存详情
- `index.tsx:797` FlatList 未绑定 `onEndReached`
- `index.tsx:799` `ListFooterComponent={null}`，无加载指示器
- 筛选模式有独立的分页逻辑（`filterPaginationRef`），不应与 hook 的 loadMore 冲突

## 设计

### 改动范围

仅修改 `OAP-app/app/(tabs)/index.tsx`，3 处改动：

1. **`onEndReached`**：`undefined` → 非 filterActive 时绑定 `loadMoreArticles`，filterActive 时传 `undefined`
2. **`onEndReachedThreshold`**：添加 `0.5`（滚动到距底部 50% 时预加载）
3. **`ListFooterComponent`**：`null` → `isLoadingMore` 时渲染 ActivityIndicator

### 交互行为

- 无筛选：滑到底部 → 加载更旧文章 → 追加到列表 → 显示 spinner
- 有筛选：不触发 load more（避免与筛选分页冲突）
- `hasMore === false`：不再触发
- `isLoadingMore` 期间：不重复触发（hook 内已有 guard）

### 不改动

- `use-articles.ts` — 逻辑完整，不需要改动
- 筛选模式的分页逻辑 — 独立机制，不在此次范围
- 后台通知 — 后续单独处理
