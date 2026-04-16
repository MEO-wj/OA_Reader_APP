SYSTEM_PROMPT_EXPECTED_PHRASES = [
    "不要暴露内部工具调用过程",
    "禁用承诺性表述",
]
SYSTEM_PROMPT_MOBILE_FORMAT_PHRASES = [
    "优先按分层列表输出，不要默认使用 Markdown 表格",
    "如果用户明确要求“用表格展示”",
    "不要混用“帖子卡片 + 表格字段”两套样式",
    "每条结果单独成段",
    "至少写出“适用对象 / 关键条件 / 关键时间或金额”三类信息中的两类",
    "优先写成 2-3 句完整说明",
]
COMPACT_PROMPT_EXPECTED_PHRASES = ["对话压缩", "【原始对话】"]

TEST_FUNCTION_CALL_USER_PROMPT = "北京天气怎么样？"
TEST_FUNCTION_CALL_TOOL_DESCRIPTION = "获取指定城市的天气"

# ─── v2 契约常量 ──────────────────────────────────────────────

# COMPACT_PROMPT_TEMPLATE 必须包含的 v2 分层保护约束
COMPACT_V2_NO_MERGE_CONSTRAINTS = [
    "不可把 hypothesized 合并到 confirmed",
]

# SYSTEM_PROMPT_TEMPLATE 必须包含的 v2 分层约束文案
SYSTEM_PROMPT_V2_CONSTRAINTS = [
    "confirmed（已确认）和 hypothesized（推测）两层",
    "禁止将 hypothesized 推测合并写入 confirmed 已确认层",
]

# ─── 两步式画像 prompt 契约常量 ──────────────────────────────

# PORTRAIT_EXTRACT_PROMPT 必须包含的关键短语
PORTRAIT_EXTRACT_REQUIRED_PHRASES = [
    "仅基于对话内容提取",
    "不参考旧画像",
    "confirmed",
    "hypothesized",
    "knowledge",
    "禁止将未经验证的行为推断写入 confirmed",
]

# PORTRAIT_MERGE_PROMPT 必须包含的关键短语
PORTRAIT_MERGE_REQUIRED_PHRASES = [
    "旧画像 JSON",
    "新画像 JSON",
    "冲突时新信息优先",
    "去重",
    "hypothesized 不升入 confirmed",
    "空字段保留旧值",
]

