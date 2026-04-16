# 无限滚动加载更多 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将首页 FlatList 的滚动加载更多功能接通，使用户滑到底部时自动加载更旧文章。

**Architecture:** 仅修改 `index.tsx`，将已有的 `loadMoreArticles()` hook 方法绑定到 FlatList 的 `onEndReached`，并添加 loading footer。无筛选时启用，筛选模式下禁用。

**Tech Stack:** React Native FlatList, Expo

---

### Task 1: 绑定 onEndReached

**Files:**
- Modify: `OAP-app/app/(tabs)/index.tsx:797`

**Step 1: 修改 onEndReached 属性**

将 `index.tsx:797` 从：
```tsx
onEndReached={undefined}
```
改为：
```tsx
onEndReached={!filterActive ? loadMoreArticles : undefined}
```

**Step 2: 添加 onEndReachedThreshold**

在 `onEndReached` 下方添加：
```tsx
onEndReachedThreshold={0.5}
```

**Step 3: 替换 ListFooterComponent**

将 `index.tsx:799` 从：
```tsx
ListFooterComponent={null}
```
改为：
```tsx
ListFooterComponent={isLoadingMore ? (
  <View style={styles.loadingMoreFooter}>
    <ActivityIndicator size="small" color={colors.gold500} />
  </View>
) : null}
```

**Step 4: 添加 footer 样式**

在 `index.tsx` 的 StyleSheet 中添加：
```ts
loadingMoreFooter: {
  paddingVertical: 16,
  alignItems: 'center',
},
```

**Step 5: 验证**

1. `cd OAP-app && npm start`
2. 在 Web/Android 模拟器打开首页
3. 确认今日要闻正常加载
4. 滑动到底部，确认 loading spinner 出现并加载更旧文章
5. 持续滑动直到 `has_more === false`，确认不再触发加载
6. 打开筛选面板，选择日期范围，确认筛选模式下不触发 load more
7. 下拉刷新后重新滑动，确认功能正常
