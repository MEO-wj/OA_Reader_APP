"""兼容编排服务 - 将旧 JSON API 请求桥接到新 ChatClient 事件流。

CompatService 负责两件事：
1. ``ask``      — 聚合 ChatClient 事件流为单个 JSON 响应，兼容旧 /ask 接口
2. ``clear_memory`` — 创建新会话（不删除旧数据），兼容旧 /clear_memory 接口
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.config.settings import Config
from src.db.memory import MemoryDB

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _today_range(tz_name: str | None) -> tuple[datetime, datetime]:
    """返回"今天"在指定时区下的 UTC 时间范围 [start_utc, end_utc)。

    Args:
        tz_name: IANA 时区名称（如 ``"Asia/Shanghai"``）。
                 为 ``None`` 时默认使用 UTC+8（中国标准时间）。

    Returns:
        (start_utc, end_utc) — 均带 ``timezone.utc`` 信息。
    """
    if tz_name:
        tz: ZoneInfo | timezone = ZoneInfo(tz_name)
    else:
        tz = timezone(timedelta(hours=8))  # 默认中国标准时间

    now_in_tz = datetime.now(tz)
    start_of_day = now_in_tz.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    start_utc = start_of_day.astimezone(timezone.utc)
    end_utc = end_of_day.astimezone(timezone.utc)
    return start_utc, end_utc


def build_runtime_hints(
    top_k: Any = None,
    display_name: str | None = None,
) -> dict[str, str]:
    """根据旧 /ask 请求参数构建运行时提示。

    将 ``top_k`` 和 ``display_name`` 转换为可追加到用户问题末尾的提示文本。

    Args:
        top_k:        用户期望的返回条数。仅当为正整数（或可解析为正整数的字符串）时生效。
        display_name: 用户显示名称。非空时生成称呼提示。

    Returns:
        键为提示类别（``"top_k"`` / ``"display_name"``），值为提示文本的字典。
        无有效提示时返回空字典。
    """
    hints: dict[str, str] = {}

    # --- top_k 处理 ---
    parsed_top_k: int | None = None
    if isinstance(top_k, int) and not isinstance(top_k, bool):
        parsed_top_k = top_k
    elif isinstance(top_k, str):
        try:
            parsed_top_k = int(top_k)
        except (ValueError, TypeError):
            pass

    if parsed_top_k is not None and parsed_top_k > 0:
        hints["top_k"] = f"请优先返回前 {parsed_top_k} 条相关结果"

    # --- display_name 处理 ---
    if display_name:
        hints["display_name"] = f"可酌情称呼用户为{display_name}"

    return hints


# ---------------------------------------------------------------------------
# CompatService
# ---------------------------------------------------------------------------

class CompatService:
    """旧 AI End 兼容编排服务。"""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()

    # -- 依赖注入钩子（方便单测 monkeypatch） --

    def _create_memory_db(self) -> MemoryDB:
        """创建 MemoryDB 实例（可在测试中被替换）。"""
        return MemoryDB()

    async def _create_chat_client(
        self,
        config: Config,
        user_id: str | None,
        conversation_id: str | None,
    ):
        """创建 ChatClient 实例（可在测试中被替换）。"""
        from src.di.providers import create_chat_client
        return await create_chat_client(config, user_id, conversation_id)

    # -- 会话解析 --

    async def _resolve_session(
        self,
        user_id: str,
    ) -> tuple[str, bool]:
        """根据 user_id 解析/创建当天会话。

        Returns:
            (conversation_id, session_created)
        """
        db = self._create_memory_db()

        # 用 config 中的时区计算"今天"的 UTC 范围
        start_utc, end_utc = _today_range(self.config.ai_compat_timezone)

        session = await db.get_latest_session_in_utc_range(
            user_id, start_utc, end_utc,
        )

        if session:
            conversation_id = str(session["conversation_id"])
            return conversation_id, False

        # 无当天会话 → 创建新的
        new_id = uuid.uuid4().hex[:8]
        await db.create_session(user_id, new_id, "新会话")
        return new_id, True

    # -- 事件聚合 --

    @staticmethod
    def _aggregate_events(
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """将 ChatClient 事件列表聚合为单个 JSON 字典。

        事件类型：
          - ``delta``      → 拼接 content 到 answer
          - ``tool_result``→ 解析 result 中的列表追加到 related_articles
          - ``done``       → 忽略（标记结束）
          - ``error``      → 记录错误信息
        """
        answer_parts: list[str] = []
        related_articles: list[Any] = []
        error_message: str | None = None

        for event in events:
            event_type = event.get("type", "")

            if event_type == "delta":
                content = event.get("content", "")
                if content:
                    answer_parts.append(content)

            elif event_type == "tool_result":
                raw_result = event.get("result", "")
                if isinstance(raw_result, str):
                    try:
                        parsed = json.loads(raw_result)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "Failed to parse tool_result as JSON: %s",
                            raw_result[:200],
                        )
                        parsed = None
                else:
                    parsed = raw_result

                # 解析后的数据可能是列表或 dict
                if isinstance(parsed, list):
                    related_articles.extend(parsed)
                elif isinstance(parsed, dict):
                    # 尝试从 dict 中提取 results 列表
                    results = parsed.get("results", [])
                    if results:
                        related_articles.extend(results)
                    else:
                        related_articles.append(parsed)

            elif event_type == "error":
                msg = event.get("message", "")
                if msg:
                    error_message = msg

        result: dict[str, Any] = {
            "answer": "".join(answer_parts),
            "related_articles": related_articles,
        }
        if error_message is not None:
            result["error"] = error_message

        return result

    # -- 公开接口 --

    async def ask(
        self,
        question: str,
        user_id: str | None = None,
        top_k: Any = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """兼容旧 /ask 接口：聚合事件流，返回单个 JSON。

        Args:
            question:     用户问题
            user_id:      用户 ID（可选）。为 None 时跳过会话管理。
            top_k:        用户期望的返回条数（可选）。
            display_name: 用户显示名称（可选）。

        Returns:
            至少包含 ``answer`` 和 ``related_articles`` 的字典。
            当 ``user_id`` 存在时，额外包含 ``conversation_id`` 和 ``session_created``。
        """
        conversation_id: str | None = None
        session_created: bool = False

        # 1) 构建运行时提示并追加到问题
        hints = build_runtime_hints(top_k=top_k, display_name=display_name)
        if hints:
            hint_text = "\n".join(hints.values())
            effective_question = f"{question}\n{hint_text}"
        else:
            effective_question = question

        # 2) 会话解析（仅 user_id 存在时）
        if user_id:
            conversation_id, session_created = await self._resolve_session(user_id)

        # 3) 创建 ChatClient 并收集事件
        client = await self._create_chat_client(
            self.config, user_id, conversation_id,
        )

        collected_events: list[dict[str, Any]] = []
        async for event in client.chat_stream_async(effective_question):
            collected_events.append(event)

        # 4) 聚合事件
        result = self._aggregate_events(collected_events)

        # 5) 附加会话字段（仅 user_id 存在时）
        if user_id:
            result["conversation_id"] = conversation_id
            result["session_created"] = session_created

        return result

    async def clear_memory(self, user_id: str | None = None) -> dict[str, Any]:
        """兼容旧 /clear_memory 接口：创建新会话。

        新语义：不删除旧数据，而是为用户创建一个新的会话。

        Args:
            user_id: 用户 ID（必须提供）。

        Returns:
            ``{"cleared": True, "conversation_id": "..."}``

        Raises:
            ValueError: user_id 为 None 时
        """
        if not user_id:
            raise ValueError("clear_memory requires a user_id")

        new_id = uuid.uuid4().hex[:8]
        db = self._create_memory_db()
        await db.create_session(user_id, new_id, "新会话")

        return {"cleared": True, "conversation_id": new_id}

    async def embed(self, text: str) -> list[float]:
        """兼容旧 /embed 接口：调用 generate_embedding 返回向量。

        Args:
            text: 需要生成向量的文本。

        Returns:
            浮点数向量列表。
        """
        from src.core.base_retrieval import generate_embedding

        return await generate_embedding(text)
