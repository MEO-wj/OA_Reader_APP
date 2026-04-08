SYSTEM_PROMPT_EXPECTED_PHRASES = [
    "不要暴露内部工具调用过程",
    "禁用承诺性表述",
]
COMPACT_PROMPT_EXPECTED_PHRASES = ["对话压缩", "【原始对话】"]

TEST_FUNCTION_CALL_USER_PROMPT = "北京天气怎么样？"
TEST_FUNCTION_CALL_TOOL_DESCRIPTION = "获取指定城市的天气"

# ─── v2 契约常量 ──────────────────────────────────────────────

# MEMORY_PROMPT_TEMPLATE 必须包含的 v2 JSON 字段路径
MEMORY_V2_REQUIRED_FIELDS = [
    "confirmed",
    "hypothesized",
    "knowledge",
    "confirmed_facts",
    "pending_queries",
]

# MEMORY_PROMPT_TEMPLATE 必须包含的 v2 约束文案
MEMORY_V2_REQUIRED_CONSTRAINTS = [
    "禁止仅凭 OA 阅读记录写 confirmed.identity",
]

# COMPACT_PROMPT_TEMPLATE 必须包含的 v2 分层保护约束
COMPACT_V2_NO_MERGE_CONSTRAINTS = [
    "不可把 hypothesized 合并到 confirmed",
]

# SYSTEM_PROMPT_TEMPLATE 必须包含的 v2 分层约束文案
SYSTEM_PROMPT_V2_CONSTRAINTS = [
    "confirmed（已确认）和 hypothesized（推测）两层",
    "禁止将 hypothesized 推测合并写入 confirmed 已确认层",
]

# FORM_MEMORY_PROMPT_TEMPLATE 必须包含的 v2 语义层标签
FORM_MEMORY_V2_REQUIRED_FIELDS = [
    "confirmed",
    "hypothesized",
    "knowledge",
    "confirmed_facts",
    "pending_queries",
]