"""用户记忆管理组件。"""

from __future__ import annotations

import json
from typing import Any

from src.chat.prompts_runtime import MEMORY_PROMPT_TEMPLATE
from src.chat.utils import _sanitize_memory_text
from src.config.settings import Config
from src.core.api_clients import get_llm_client
from src.core.api_queue import get_api_queue
from src.db.memory import MemoryDB


class MemoryManager:
    """负责画像/知识记忆的形成与保存。"""

    def __init__(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
        *,
        config: Config | None = None,
        api_queue: Any | None = None,
        memory_db: MemoryDB | None = None,
        completion_sync: Any | None = None,
    ) -> None:
        self.user_id = user_id
        self.conversation_id = conversation_id or "default"
        self._config = config
        self._api_queue = api_queue
        self._memory_db = memory_db
        self._completion_sync = completion_sync

    @property
    def config(self) -> Config:
        return self._config or Config.load()

    @property
    def api_queue(self) -> Any:
        return self._api_queue or get_api_queue()

    @property
    def memory_db(self) -> MemoryDB:
        if self._memory_db is not None:
            return self._memory_db
        return MemoryDB()

    @staticmethod
    def _skip_result(
        skip_reason: str,
    ) -> dict[str, Any]:
        """构造跳过结果的统一字典。"""
        return {
            "saved": False,
            "attempts_used": 0,
            "last_error": "",
            "skip_reason": skip_reason,
            "portrait_text": "",
            "knowledge_text": "",
        }

    async def form_memory(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """形成用户画像与知识记忆（v2 结构化返回契约 + 重试协议）。

        返回字段:
            saved: 是否成功落库
            attempts_used: LLM 调用次数
            last_error: 最后一次错误信息
            skip_reason: 跳过原因（no_user_id / no_messages / max_retries_exceeded / ""）
            portrait_text: 画像 JSON 字符串
            knowledge_text: 知识 JSON 字符串

        重试协议:
            - 最多 3 次尝试
            - 内容错误（非 JSON / v2 校验失败）可重试
            - 基础设施错误（DB 写入异常）不重试，直接上抛
        """
        if not self.user_id:
            return self._skip_result("no_user_id")

        if not messages:
            return self._skip_result("no_messages")

        max_attempts = 3
        last_error = ""

        for attempt in range(1, max_attempts + 1):
            # 构建提示词：首次用原始 prompt，重试用带错误信息的 prompt
            if attempt == 1:
                prompt = await self._build_memory_prompt(messages)
            else:
                prompt = self._build_retry_prompt(messages, last_error)

            # 调用 LLM
            response = await self.api_queue.submit(
                "llm",
                self._completion_sync or self._create_memory_completion_sync,
                prompt,
            )
            content = _sanitize_memory_text(response.choices[0].message.content or "")

            # 解析 v2 记忆
            parsed = self._parse_memory(content)

            # 判断解析是否成功：至少有一个字段非空
            if parsed["portrait_text"] or parsed["knowledge_text"]:
                # 解析成功 —— 保存到数据库（不捕获异常，让基础设施错误上抛）
                await self.memory_db.save_profile(
                    self.user_id,
                    parsed["portrait_text"],
                    parsed["knowledge_text"],
                )
                return {
                    "saved": True,
                    "attempts_used": attempt,
                    "last_error": "",
                    "skip_reason": "",
                    "portrait_text": parsed["portrait_text"],
                    "knowledge_text": parsed["knowledge_text"],
                }

            # 解析失败 —— 记录错误，准备重试
            last_error = f"第{attempt}次尝试: LLM 返回内容无法解析为有效 v2 JSON"

        # 3 次尝试全部失败
        return {
            "saved": False,
            "attempts_used": max_attempts,
            "last_error": last_error,
            "skip_reason": "max_retries_exceeded",
            "portrait_text": "",
            "knowledge_text": "",
        }

    async def _build_memory_prompt(self, messages: list[dict[str, Any]]) -> str:
        conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        existing_profile = await self._load_existing_profile()
        profile_section = ""
        if existing_profile:
            profile_section = existing_profile
        return MEMORY_PROMPT_TEMPLATE.format(
            conversation=conversation,
            existing_profile=profile_section,
        )

    async def _load_existing_profile(self) -> str:
        """从 DB 加载已有用户画像，校验 v2 格式后返回可读文本。

        v1 或非法 JSON 返回空字符串（等效于无画像）。
        DB 异常静默降级（画像注入是可选装饰，不应阻塞主流程）。
        """
        try:
            profile = await self.memory_db.get_profile(self.user_id)
        except Exception:
            return ""
        if not profile:
            return ""

        portrait_raw = profile.get("portrait_text", "") or ""
        knowledge_raw = profile.get("knowledge_text", "") or ""

        if not portrait_raw:
            return ""

        try:
            portrait_data = json.loads(portrait_raw)
        except (json.JSONDecodeError, TypeError):
            return ""

        if not isinstance(portrait_data, dict):
            return ""

        if not self._validate_v2_memory_schema(portrait_data):
            return ""

        # 注入已有画像前先复用统一裁决逻辑，避免推断项以 confirmed 身份进入 prompt。
        self._adjudicate_identity(portrait_data)

        sections: list[str] = []
        confirmed = portrait_data.get("confirmed", {})
        identity = self._normalize_string_list(confirmed.get("identity"))
        if identity:
            sections.append("已确认身份: " + ", ".join(identity))
        interests = self._normalize_string_list(confirmed.get("interests"))
        if interests:
            sections.append("已确认兴趣: " + ", ".join(interests))
        constraints = self._normalize_string_list(confirmed.get("constraints"))
        if constraints:
            sections.append("已确认约束: " + ", ".join(constraints))

        hypothesized = portrait_data.get("hypothesized", {})
        hypo_identity = self._normalize_string_list(hypothesized.get("identity"))
        if hypo_identity:
            sections.append("推测身份: " + ", ".join(hypo_identity))
        hypo_interests = self._normalize_string_list(hypothesized.get("interests"))
        if hypo_interests:
            sections.append("推测兴趣: " + ", ".join(hypo_interests))

        if knowledge_raw:
            try:
                knowledge_data = json.loads(knowledge_raw)
                if isinstance(knowledge_data, dict):
                    facts = self._normalize_string_list(knowledge_data.get("confirmed_facts"))
                    if facts:
                        sections.append("已确认事实: " + ", ".join(facts))
                    queries = self._normalize_string_list(knowledge_data.get("pending_queries"))
                    if queries:
                        sections.append("待查询事项: " + ", ".join(queries))
            except (json.JSONDecodeError, TypeError):
                pass

        return "\n".join(sections) if sections else ""

    def _build_retry_prompt(self, messages: list[dict[str, Any]], last_error: str) -> str:
        """构建重试提示词：仅包含原始对话 + 上次错误信息，不追加已保存画像。"""
        conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        base_prompt = MEMORY_PROMPT_TEMPLATE.format(
            conversation=conversation,
            existing_profile="",
        )
        return (
            f"{base_prompt}\n\n"
            f"【注意】上一次尝试失败，错误原因：{last_error}\n"
            f"请严格按要求输出合法 JSON，不要添加任何额外文本。"
        )

    def _create_memory_completion_sync(self, prompt: str) -> Any:
        client = get_llm_client()
        return client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )

    # ------------------------------------------------------------------
    # v2 记忆解析：校验 + 裁决 + 标准化
    # ------------------------------------------------------------------

    # v1 格式的特征键（存在任一即视为 v1 数据）
    _V1_KEYS = frozenset({
        "hard_constraints", "soft_constraints",
        "risk_tolerance", "verified_facts",
    })

    # 推断关键词——出现在 confirmed.identity 中即触发降级
    _INFERRAL_KEYWORDS = (
        "可能", "推测", "频繁阅读", "多次查询", "来源",
    )

    # 来源标注模式
    _SOURCE_TAG = "（来源："

    @staticmethod
    def _normalize_string_list(value: Any) -> list[str]:
        """将任意输入标准化为字符串列表。

        接受列表或单字符串，过滤非字符串和空串。
        """
        if isinstance(value, str):
            return [value] if value else []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item]
        return []

    @classmethod
    def _validate_v2_memory_schema(cls, data: dict[str, Any]) -> bool:
        """校验 JSON 是否符合 v2 记忆结构。

        - 存在 v1 特征键 → 视为非法，返回 False
        - 不含 confirmed 键 → 视为非法，返回 False
        """
        # 检测 v1 特征键
        if any(key in data for key in cls._V1_KEYS):
            return False
        # v2 至少需要 confirmed 或 hypothesized 或 knowledge
        if "confirmed" not in data:
            return False
        return True

    @classmethod
    def _adjudicate_identity(cls, portrait: dict[str, Any]) -> None:
        """对 confirmed.identity 做推断裁决：含推断关键词的条目降级到 hypothesized.identity。

        降级条目若缺少来源标注（（来源：...）），自动补上（来源未确认）前缀。
        直接修改 portrait 字典（in-place）。
        """
        confirmed = portrait.setdefault("confirmed", {})
        hypothesized = portrait.setdefault("hypothesized", {})

        confirmed_identity = cls._normalize_string_list(confirmed.get("identity"))
        hypo_identity = cls._normalize_string_list(hypothesized.get("identity"))

        keep: list[str] = []
        for item in confirmed_identity:
            if any(kw in item for kw in cls._INFERRAL_KEYWORDS):
                # 需要降级
                if cls._SOURCE_TAG in item:
                    # 已有来源标注，保持原文
                    hypo_identity.append(item)
                else:
                    # 无来源标注，补前缀
                    hypo_identity.append(f"（来源未确认）{item}")
            else:
                keep.append(item)

        confirmed["identity"] = keep
        hypothesized["identity"] = hypo_identity

    def _parse_memory(self, content: str) -> dict[str, str]:
        """解析 LLM 返回的记忆 JSON，输出 v2 结构。

        流程:
        1. JSON 解析失败 → 返回空字符串
        2. v2 校验失败（含 v1 键或缺少 confirmed） → 返回空字符串
        3. 标准化 confirmed / hypothesized / knowledge 各字段
        4. 对 portrait 执行 identity 裁决
        5. 输出 portrait_text / knowledge_text
        """
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {"portrait_text": "", "knowledge_text": ""}

        if not isinstance(data, dict):
            return {"portrait_text": "", "knowledge_text": ""}

        # v2 校验
        if not self._validate_v2_memory_schema(data):
            return {"portrait_text": "", "knowledge_text": ""}

        # 构建 portrait 对象（标准化字段）
        raw_confirmed = data.get("confirmed", {}) or {}
        raw_hypothesized = data.get("hypothesized", {}) or {}

        portrait: dict[str, Any] = {
            "confirmed": {
                "identity": self._normalize_string_list(raw_confirmed.get("identity")),
                "interests": self._normalize_string_list(raw_confirmed.get("interests")),
                "constraints": self._normalize_string_list(raw_confirmed.get("constraints")),
            },
            "hypothesized": {
                "identity": self._normalize_string_list(raw_hypothesized.get("identity")),
                "interests": self._normalize_string_list(raw_hypothesized.get("interests")),
            },
        }

        # identity 裁决（in-place 修改 portrait）
        self._adjudicate_identity(portrait)

        # 构建 knowledge 对象
        raw_knowledge = data.get("knowledge", {}) or {}
        knowledge: dict[str, Any] = {
            "confirmed_facts": self._normalize_string_list(raw_knowledge.get("confirmed_facts")),
            "pending_queries": self._normalize_string_list(raw_knowledge.get("pending_queries")),
        }

        return {
            "portrait_text": json.dumps(portrait, ensure_ascii=False),
            "knowledge_text": json.dumps(knowledge, ensure_ascii=False),
        }
