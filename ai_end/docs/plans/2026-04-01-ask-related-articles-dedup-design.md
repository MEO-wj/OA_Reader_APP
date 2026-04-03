# /ask related_articles 去重与评分聚合设计

日期: 2026-04-01

## 背景

在旧接口兼容端点 /ask 的响应中，related_articles 可能出现重复文章。重复主要来自事件聚合层：同一轮会话中多次 search_articles 工具调用结果被直接累加。

本设计目标：
- 对 related_articles 按文章 id 去重。
- 对重复命中文章的 ebd_similarity、keyword_similarity、rerank_score 分别按各自平均值计算。
- 平均值规则为仅统计非空值（None 不参与分母）。

## 需求确认

- 去重主键: 仅使用 id。
- 平均值规则: 非空参与分母，空值不参与。

## 方案对比

### 方案 1（推荐）: 在兼容聚合层去重与聚合

在 compat_service 的事件聚合逻辑中，将所有 search_articles 结果汇总后统一按 id 去重并聚合评分。

优点:
- 精准修复当前问题来源。
- 改动面小，对核心检索层无侵入。
- 技术债最低，便于快速回归验证。

缺点:
- 如未来其他入口需要同样规则，需抽取公共组件。

### 方案 2: 在检索层去重与聚合

在 article_retrieval.search_articles 返回前统一处理。

优点:
- 理论上所有调用方受益。

缺点:
- 当前重复并非主要出在单次检索结果内，收益不聚焦。
- 可能影响现有 rerank 语义和调试定位。

### 方案 3: 双层兜底

检索层和兼容层同时处理。

优点:
- 容错最强。

缺点:
- 规则重复，维护成本高，不符合当前 YAGNI。

## 最终设计

采用方案 1，在兼容层做一次性统一聚合。

### 架构与职责

- 保持 /ask 响应结构不变，仅优化 related_articles 内容质量。
- 在 CompatService 内新增私有聚合辅助逻辑，不改动公开接口签名。

### 组件设计

1) 标准化函数
- 名称建议: _normalize_tool_result_to_docs(parsed)
- 职责:
  - 兼容 list、{"results": [...]}、单个 dict 三种结构。
  - 过滤非 dict 项。
  - 为每篇文档补 summary_snippet（复用 _truncate_text）。

2) 去重聚合函数
- 名称建议: _dedupe_and_aggregate_docs(docs)
- 输入: 标准化后的文档列表。
- 核心状态:
  - by_id 映射（id -> 聚合条目）
  - passthrough_docs（无 id 文档，按兼容策略透传）
- 字段合并规则:
  - 展示字段（title、unit、summary 等）优先保留首个非空值，后续仅补空。
  - 三个评分字段分别维护 sum 与 count。
  - 平均值计算:
    - ebd_similarity = ebd_sum / ebd_count（count 为 0 则 None）
    - keyword_similarity = keyword_sum / keyword_count（count 为 0 则 None）
    - rerank_score = rerank_sum / rerank_count（count 为 0 则 None）

### 数据流

- _aggregate_events 遍历事件时，仍只接收 tool=search_articles。
- 每次 tool_result 先解析，再标准化到文档列表，累计到 all_docs。
- 事件遍历结束后，统一执行去重聚合，得到最终 related_articles。

## 错误处理与可观测性

- tool_result JSON 解析失败: 记录 warning 并跳过该批次，不影响 answer。
- 非法文档元素: 过滤。
- 无 id 文档: 不参与去重与平均值，透传保留。
- 非法评分值: 视为无效，不计入平均值。
- 建议新增聚合后日志:
  - total_docs、deduped_docs、no_id_docs。

## 测试设计

目标文件: tests/unit/test_compat_service.py

新增/调整用例:
1. 同一 id 跨多次 tool_result 重复，仅保留一条。
2. 三个评分字段按各自非空样本平均值计算。
3. 无 id 文档透传，不参与聚合。
4. 三种 tool_result 结构（list/dict(results)/dict）都可被聚合。
5. 非法评分值容错，不抛异常且不污染平均值分母。

回归验证:
- tests/integration/test_compat_endpoints.py 保持通过。

## 实施边界

- 不修改 /ask 请求模型。
- 不调整 article_retrieval 的排序与召回策略。
- 不更改会话管理、clear_memory、embed 逻辑。

## 实施记录

### 实现点位

- `src/api/compat_service.py`
  - `_normalize_tool_result_to_docs()` — 标准化 tool_result 为文档列表（兼容 list / dict(results) / dict）
  - `_dedupe_and_aggregate_docs()` — 按 id 去重 + 评分均值聚合 + 无 id 文档透传
  - `_aggregate_events()` — 重构为累积 all_docs 后统一调用去重聚合

### 新增测试

- `tests/unit/test_compat_service.py`
  - `test_aggregate_events_dedup_by_id_and_average_scores` — 同 id 去重 + 三评分字段各自均值
  - `test_aggregate_events_keeps_no_id_docs_passthrough` — 无 id 文档透传
  - `test_display_field_skips_none_and_empty_takes_first_nonempty` — 展示字段取首个非空值
  - `test_display_field_all_empty_falls_back_to_empty` — 全空时保留空值
  - `test_aggregate_events_ignores_invalid_score_values` — 非法评分值（字符串/bool/NaN）过滤

### 平均值规则说明

- 三个评分字段（ebd_similarity、keyword_similarity、rerank_score）各自独立计算平均值
- 仅 `isinstance(v, (int, float))` 且非 bool、非 NaN 的值参与 sum 和 count
- count 为 0 时该字段输出 None
- 展示字段（title、unit、summary 等）保留首个非 None 且非空字符串的值

### 回归验证结果

- `tests/unit/test_compat_service.py` — PASS（全部用例通过）
- `tests/integration/test_compat_endpoints.py` — PASS（11 passed，契约无破坏）

## 验收标准

- related_articles 中同一 id 最多出现一次。
- 三个评分字段在重复命中时按各自非空平均值输出。
- 老接口响应结构不变且集成测试通过。
