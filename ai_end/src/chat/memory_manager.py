"""用户记忆管理组件。"""

from __future__ import annotations

import json
from typing import Any

from src.chat.prompts_runtime import PORTRAIT_EXTRACT_PROMPT, PORTRAIT_MERGE_PROMPT
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
        """形成用户画像与知识记忆（v2 两步式：提取 + 合并）。

        返回字段:
            saved: 是否成功落库
            attempts_used: LLM 调用次数（extract + merge 总计）
            last_error: 最后一次错误信息
            skip_reason: 跳过原因（no_user_id / no_messages / max_retries_exceeded / ""）
            portrait_text: 画像 JSON 字符串
            knowledge_text: 知识 JSON 字符串

        两步式流程:
            1. Extract: 从对话中提取画像（不参考旧画像）
            2. Merge: 若有旧画像，将新旧画像合并；否则直接保存 extract 结果
        """
        if not self.user_id:
            return self._skip_result("no_user_id")

        if not messages:
            return self._skip_result("no_messages")

        # ── Step 1: Extract ──────────────────────────────────────────
        extracted = await self._extract_portrait(messages)
        if not extracted["portrait_text"] and not extracted["knowledge_text"]:
            # extract 全部重试失败
            return {
                "saved": False,
                "attempts_used": extracted["attempts_used"],
                "last_error": extracted["last_error"],
                "skip_reason": "max_retries_exceeded",
                "portrait_text": "",
                "knowledge_text": "",
            }

        # ── 判断是否有已有画像（决定快速路径 or 合并路径） ──────────
        existing_profile = await self._load_existing_profile_raw()
        if not existing_profile:
            # 快速路径：无已有画像，直接保存 extract 结果
            await self.memory_db.save_profile(
                self.user_id,
                extracted["portrait_text"],
                extracted["knowledge_text"],
            )
            return {
                "saved": True,
                "attempts_used": extracted["attempts_used"],
                "last_error": "",
                "skip_reason": "",
                "portrait_text": extracted["portrait_text"],
                "knowledge_text": extracted["knowledge_text"],
            }

        # ── Step 2: Merge ────────────────────────────────────────────
        merged = await self._merge_portraits(existing_profile, extracted)

        if merged["portrait_text"] == "" and merged["knowledge_text"] == "":
            # merge 失败，回退到 extract 结果
            await self.memory_db.save_profile(
                self.user_id,
                extracted["portrait_text"],
                extracted["knowledge_text"],
            )
            return {
                "saved": True,
                "attempts_used": extracted["attempts_used"] + merged["attempts_used"],
                "last_error": "merge全部重试失败，回退到extract结果",
                "skip_reason": "",
                "portrait_text": extracted["portrait_text"],
                "knowledge_text": extracted["knowledge_text"],
            }

        # merge 成功，保存合并结果
        await self.memory_db.save_profile(
            self.user_id,
            merged["portrait_text"],
            merged["knowledge_text"],
        )
        return {
            "saved": True,
            "attempts_used": extracted["attempts_used"] + merged["attempts_used"],
            "last_error": "",
            "skip_reason": "",
            "portrait_text": merged["portrait_text"],
            "knowledge_text": merged["knowledge_text"],
        }

    async def _load_existing_profile_raw(self) -> dict[str, str] | None:
        """从 DB 加载已有用户画像的原始数据，校验 v2 格式后返回。

        返回 dict: {"portrait_text": str, "knowledge_text": str} 或 None。
        v1 格式、非法 JSON、无画像均返回 None。
        DB 异常静默降级（画像注入是可选装饰，不应阻塞主流程）。
        """
        try:
            profile = await self.memory_db.get_profile(self.user_id)
        except Exception:
            return None
        if not profile:
            return None

        portrait_raw = profile.get("portrait_text", "") or ""
        knowledge_raw = profile.get("knowledge_text", "") or ""

        if not portrait_raw:
            return None

        try:
            portrait_data = json.loads(portrait_raw)
        except (json.JSONDecodeError, TypeError):
            return None

        if not isinstance(portrait_data, dict):
            return None

        if not self._validate_v2_memory_schema(portrait_data):
            return None

        return {"portrait_text": portrait_raw, "knowledge_text": knowledge_raw}

    async def _extract_portrait(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Step 1: 仅从对话中提取画像，不参考旧画像。

        使用 PORTRAIT_EXTRACT_PROMPT，最多重试 3 次。
        返回 dict:
            portrait_text: 画像 JSON 字符串（成功时）或空串（全部失败时）
            knowledge_text: 知识 JSON 字符串
            attempts_used: 实际 LLM 调用次数
            last_error: 最后一次错误（成功时为空串）
        """
        max_attempts = 3
        last_error = ""
        conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

        for attempt in range(1, max_attempts + 1):
            prompt = PORTRAIT_EXTRACT_PROMPT.format(conversation=conversation)
            if attempt > 1 and last_error:
                prompt = (
                    f"{prompt}\n\n"
                    f"【上次错误】{last_error}\n"
                    "请严格输出合法 v2 JSON，不要添加任何额外文本。"
                )

            response = await self.api_queue.submit(
                "llm",
                self._completion_sync or self._create_memory_completion_sync,
                prompt,
            )
            content = _sanitize_memory_text(response.choices[0].message.content or "")
            parsed = self._parse_memory(content)

            if parsed["portrait_text"] or parsed["knowledge_text"]:
                return {
                    "portrait_text": parsed["portrait_text"],
                    "knowledge_text": parsed["knowledge_text"],
                    "attempts_used": attempt,
                    "last_error": "",
                }

            last_error = f"第{attempt}次尝试: LLM 返回内容无法解析为有效 v2 JSON"

        return {
            "portrait_text": "",
            "knowledge_text": "",
            "attempts_used": max_attempts,
            "last_error": last_error,
        }

    async def _merge_portraits(
        self, existing_profile: dict[str, str], extracted: dict[str, Any],
    ) -> dict[str, Any]:
        """Step 2: 将旧画像与新提取的画像合并。

        使用 PORTRAIT_MERGE_PROMPT，最多重试 3 次。
        返回 dict:
            portrait_text: 合并后的画像 JSON 字符串
            knowledge_text: 合并后的知识 JSON 字符串
            attempts_used: 实际 LLM 调用次数
        全部重试失败返回空结果：portrait_text/knowledge_text 为空串。
        """
        max_attempts = 3
        last_error = ""

        # 构建新画像 JSON：合并 portrait + knowledge 供 LLM 参考
        new_portrait_obj: dict[str, Any] = {}
        if extracted.get("portrait_text"):
            try:
                portrait_data = json.loads(extracted["portrait_text"])
                new_portrait_obj.update(portrait_data)
            except (json.JSONDecodeError, TypeError):
                pass
        if extracted.get("knowledge_text"):
            try:
                knowledge_data = json.loads(extracted["knowledge_text"])
                new_portrait_obj["knowledge"] = knowledge_data
            except (json.JSONDecodeError, TypeError):
                pass

        new_portrait_json = json.dumps(new_portrait_obj, ensure_ascii=False)

        # 旧画像输入也需携带 knowledge，保证 merge 可执行"空字段保留旧值"。
        old_profile_obj: dict[str, Any] = {}
        old_portrait_raw = existing_profile.get("portrait_text", "{}")
        old_knowledge_raw = existing_profile.get("knowledge_text", "")

        try:
            old_portrait_data = json.loads(old_portrait_raw)
            if isinstance(old_portrait_data, dict):
                old_profile_obj.update(old_portrait_data)
        except (json.JSONDecodeError, TypeError):
            pass

        if old_knowledge_raw:
            try:
                old_knowledge_data = json.loads(old_knowledge_raw)
                if isinstance(old_knowledge_data, dict):
                    old_profile_obj["knowledge"] = old_knowledge_data
            except (json.JSONDecodeError, TypeError):
                pass

        old_portrait_json = json.dumps(old_profile_obj, ensure_ascii=False)

        for attempt in range(1, max_attempts + 1):
            prompt = PORTRAIT_MERGE_PROMPT.format(
                old_portrait=old_portrait_json,
                new_portrait=new_portrait_json,
            )
            if attempt > 1 and last_error:
                prompt = (
                    f"{prompt}\n\n"
                    f"【上次错误】{last_error}\n"
                    "请严格输出合法 v2 JSON，不要添加任何额外文本。"
                )

            response = await self.api_queue.submit(
                "llm",
                self._completion_sync or self._create_memory_completion_sync,
                prompt,
            )
            content = _sanitize_memory_text(response.choices[0].message.content or "")
            parsed = self._parse_memory(content)

            if parsed["portrait_text"] or parsed["knowledge_text"]:
                return {
                    "portrait_text": parsed["portrait_text"],
                    "knowledge_text": parsed["knowledge_text"],
                    "attempts_used": attempt,
                }

            last_error = f"第{attempt}次尝试: LLM 返回内容无法解析为有效 v2 JSON"

        # 全部重试失败返回含 attempts_used 的 dict（而非 None）
        return {
            "portrait_text": "",
            "knowledge_text": "",
            "attempts_used": max_attempts,
        }

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
