---
name: document-retrieval
description: 通用文档检索工具，支持向量搜索与内容定位。适用于需要在知识库中查找、比对、引用文档内容的场景。
verification_token: DOCUMENT-RETRIEVAL-GENERIC-2026
---

# 使用场景

当用户需要从文档库中查找事实依据、定位细节段落、或对比多个文档时使用此技能。

## 典型触发

- "查找关于报销规则的文档依据"
- "定位合同里关于违约责任的条款"
- "对比两份方案在交付范围上的差异"
- "提取某个流程文档里的关键步骤"

# 可用工具

## search_documents

向量搜索相关文档，返回匹配文档的标题和摘要。

**参数:**
- `query` (string, 必需): 搜索查询文本
- `keywords` (string, 可选): 关键词，逗号分隔
- `top_k` (integer, 可选): 返回结果数量，默认 10
- `threshold` (float, 可选): 相似度阈值，默认 0.5

**返回:** 匹配文档列表，每个包含 id、title、summary、ebd_similarity、keyword_similarity、rerank_score

## grep_document

获取指定文档的具体内容，支持多种搜索模式。

**参数:**
- `document_id` (integer, 必需): 文档 ID
- `mode` (string, 可选): 搜索模式
  - `"auto"`: 自动检测（默认）
  - `"summary"`: 返回文档前500字摘要
  - `"keyword"`: 关键词精确匹配
  - `"regex"`: 正则表达式匹配
  - `"section"`: 章节标题提取
  - `"line_range"`: 精确行范围
- `keyword` (string, 可选): 关键词（mode=`"keyword"` 时）
- `section` (string, 可选): 章节标题（mode=`"section"` 时）
- `pattern` (string, 可选): 正则表达式（mode=`"regex"` 时）
- `context_lines` (integer, 可选): 上下文行数，默认 0
- `max_results` (integer, 可选): 最大结果数，默认 3
- `start_line`/`end_line` (integer, 可选): 行范围（mode=`"line_range"` 时）

**返回格式:**
```json
{
  "status": "success | not_found | error",
  "data": {
    "title": "文档标题",
    "matches": [
      {
        "content": "匹配的内容",
        "line_number": 23,
        "context_before": ["前文..."],
        "context_after": ["后文..."],
        "highlight_ranges": [[5, 8]]
      }
    ]
  },
  "metadata": {
    "total_matches": 5,
    "search_mode": "keyword"
  }
}
```

## grep_documents

跨多个文档搜索内容。

**参数:**
- `document_ids` (array, 必需): 文档 ID 列表
- `keyword`/`section`/`pattern`: 搜索条件
- `mode` (string, 可选): 搜索模式
- `context_lines`/`max_results`: 结果控制

**返回:** 多个文档的匹配结果汇总

# 使用建议

1. **先搜索**：使用 `search_documents` 搜索相关文档
2. **看摘要**：根据返回摘要选择最相关文档
3. **取详情**：使用 `grep_document` 获取具体内容
   - 获取概览：`mode="summary"`
   - 查找条款：`mode="keyword"` + `context_lines=2`
   - 多种表述：`mode="regex"` + 正则模式
4. **做对比**：使用 `grep_documents` 对比多个文档
5. **防幻觉约束**：若最终证据不足，需明确说明“当前证据不足以确认”，但不要暴露工具名、参数、`status` 等中间检索细节

# 输出风格

- 清晰引用来源：根据《[文档标题]》第X条...
- 摘要优先：先给结论，再展开细节
- 实用导向：强调对用户最有用的条款

# 注意事项

- 本技能仅提供文档检索和内容提取，不替代业务决策
- 文档内容可能更新，建议在关键决策前复核最新版本
- 高风险场景下建议结合原始文件与权威渠道复核
