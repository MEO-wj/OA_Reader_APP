# AI 端时间感知能力设计

## 背景

当前 AI 端（ai_end）存在三个缺口：

1. 系统提示词没有当前日期，模型对"今天"、"这周"等时间表达理解不稳定。
2. `search_articles` 不能按日期范围检索，无法做精确时间窗口查询。
3. 搜索排序对时效性利用不足，新旧文章区分不明显。

## 决策结论

采用方案 A（提示词注入 + 工具参数扩展 + 检索层日期过滤 + 温和时效性加权）。

约束确认：

1. 初版不做服务端自然语言时间词解析（如"这周"到日期范围的规则解析）。
2. 时间词理解依赖模型 + 系统提示中的当前日期。
3. 日期范围过滤仅在工具显式传入 `start_date` / `end_date` 时生效。

该方案在满足需求的同时，新增模块最少、兼容性最好、未来可平滑扩展，技术债最低。

## 设计详情

### 1. 时间感知注入（聊天层）

改动文件：

- `ai_end/src/chat/prompts_runtime.py`
- `ai_end/src/chat/client.py`

设计：

1. 在 `SYSTEM_PROMPT_TEMPLATE` 顶部新增占位符：`当前日期：{current_date}（{weekday}）`
2. 在 `_build_system_prompt()` 中按 `AI_COMPAT_TZ` 读取时区（当前配置 `Asia/Shanghai`）
3. 使用该时区生成日期和星期并注入模板

目标效果：模型在不增加新工具的前提下，能够更稳定地理解相对时间表达。

### 2. 检索工具契约扩展（工具层）

改动文件：

- `ai_end/skills/article-retrieval/TOOLS.md`

`search_articles` 参数调整：

1. `query` 由必填改为可选，支持纯时间类查询（例如"最新 OA"）
2. 新增 `start_date`（可选，`YYYY-MM-DD`）
3. 新增 `end_date`（可选，`YYYY-MM-DD`）

兼容性策略：

1. 老调用方不传日期参数时，行为保持兼容。
2. 日期参数仅作为附加过滤，不改变已有字段语义。

### 3. 查询执行与排序（检索层）

改动文件：

- `ai_end/src/core/article_retrieval.py`

数据流：

1. 有 `query`：向量搜索 + 可选关键词搜索 + 合并 + rerank
2. 无 `query`：跳过向量/关键词，直接走按 `published_on DESC` 的时间排序分支
3. 若日期参数合法，在上述分支中统一追加日期过滤条件

时效性加权：

使用温和惩罚公式（不覆盖语义相关性主导地位）：

`final_score = similarity - 0.1 * exp(-days_old / 30)`

说明：

1. 同等语义相似度下，新文章会略微靠前
2. 对旧但高度相关文章仍保留可见性

## 错误处理与边界行为

1. `start_date > end_date`：自动交换后执行
2. 日期格式错误：忽略非法参数，退化为无该参数过滤
3. 仅传 `start_date`：`end_date` 默认当前日期（基于 `AI_COMPAT_TZ`）
4. 仅传 `end_date`：不设置下界
5. `query` 为空：不报错，走时间排序分支

## TDD 测试计划

1. 提示词注入测试
        - 验证 `_build_system_prompt()` 输出包含正确日期和星期
2. 日期过滤 SQL 测试
        - 验证日期参数传入后 SQL 包含正确过滤条件
3. 时效性加权测试
        - 验证相同相似度下新文章 `final_score` 更高
4. 边界行为测试
        - 覆盖日期反转、非法日期、单边界场景
5. 纯时间查询测试
        - 验证 `query` 为空时跳过 embedding 并按日期降序返回

## 涉及文件

| 文件 | 变更内容 |
|------|----------|
| `ai_end/src/chat/prompts_runtime.py` | 增加日期占位符 |
| `ai_end/src/chat/client.py` | 注入 `current_date` 和 `weekday` |
| `ai_end/skills/article-retrieval/TOOLS.md` | `search_articles` 参数扩展 |
| `ai_end/src/core/article_retrieval.py` | 日期过滤、空 query 分支、时效性加权 |
| `ai_end/tests/unit/test_article_retrieval.py` | 新增对应单元测试 |
