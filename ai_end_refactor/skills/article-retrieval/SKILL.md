---
name: article-retrieval
description: OA文章检索工具，支持向量搜索与内容定位。适用于在学校OA公告中查找事实依据、定位细节段落、或对比多篇文章的场景。
verification_token: ARTICLE-RETRIEVAL-OA-2026
---

# 使用场景

当用户需要从学校OA公告中查找通知、定位具体条款、或对比多篇文章时使用此技能。

## 典型触发

- "查找关于期末考试安排的通知"
- "定位请假制度里关于事假的规定"
- "对比两份通知在报到时间上的差异"
- "提取某个通知里的关键步骤"

# 可用工具

## search_articles

向量搜索相关文章，返回匹配文章的标题、发布单位和摘要。

**参数:**
- `query` (string, 必需): 搜索查询文本
- `keywords` (string, 可选): 关键词，逗号分隔
- `top_k` (integer, 可选): 返回结果数量，默认 10
- `threshold` (float, 可选): 相似度阈值，默认 0.5

## grep_article

获取指定文章的具体内容，支持多种搜索模式。

**参数:**
- `article_id` (integer, 必需): 文章 ID
- `mode` (string, 可选): 搜索模式 (auto/summary/keyword/regex/section/line_range)
- `keyword` (string, 可选): 关键词
- `section` (string, 可选): 章节标题
- `pattern` (string, 可选): 正则表达式
- `context_lines` (integer, 可选): 上下文行数
- `max_results` (integer, 可选): 最大结果数
- `start_line`/`end_line` (integer, 可选): 行范围

## grep_articles

跨多个文章搜索内容。

# 使用建议

1. **先搜索**：使用 `search_articles` 搜索相关文章
2. **看摘要**：根据返回摘要选择最相关文章
3. **取详情**：使用 `grep_article` 获取具体内容
4. **做对比**：使用 `grep_articles` 对比多个文章
5. **防幻觉约束**：若最终证据不足，需明确说明"当前证据不足以确认"，不要暴露工具名、参数、`status` 等中间检索细节

# 输出风格

- 清晰引用来源：根据《[文章标题]》（发布单位，发布日期）
- 摘要优先：先给结论，再展开细节
- 实用导向：强调对用户最有用的条款
