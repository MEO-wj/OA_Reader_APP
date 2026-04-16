"""兼容编排服务 - 将旧 JSON API 请求桥接到新 ChatClient 事件流。

CompatService 负责两件事：
1. ``clear_memory`` — 创建新会话（不删除旧数据），兼容旧 /clear_memory 接口
2. ``embed``        — 调用 generate_embedding 返回向量，兼容旧 /embed 接口
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from src.config.settings import Config
from src.db.memory import MemoryDB

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _today_range(tz_name: str = "UTC") -> tuple[datetime, datetime]:
    """按指定时区计算"今天"的 naive datetime 范围 [start, end)。

    Args:
        tz_name: IANA 时区名（如 "Asia/Shanghai"），默认 "UTC"。

    Returns:
        (start, end) — 均为 naive datetime，值与该时区的本地时间一致。
    """
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name)
    except (KeyError, Exception):
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


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

    # -- 会话解析 --

    async def _resolve_timezone(self) -> str:
        """解析有效时区：config > DB SHOW TIMEZONE > UTC。"""
        tz = getattr(self.config, "compat_timezone", None)
        if tz:
            return tz
        db = self._create_memory_db()
        if hasattr(db, "get_db_timezone"):
            db_tz = await db.get_db_timezone()
            if db_tz:
                return db_tz
        return "UTC"

    # -- 公开接口 --

    async def clear_memory(self, user_id: str | None = None) -> dict[str, Any]:
        """兼容旧 /clear_memory 接口：创建或复用当天会话。

        查询当天最新会话：
          1. 会话存在且有消息 → 创建新会话
          2. 会话存在但无消息 → 复用现有会话
          3. 无当天会话 → 创建新会话

        Args:
            user_id: 用户 ID（必须提供）。

        Returns:
            ``{"cleared": True, "conversation_id": "..."}``

        Raises:
            ValueError: user_id 为 None 时
        """
        if not user_id:
            raise ValueError("clear_memory requires a user_id")

        db = self._create_memory_db()
        tz_name = await self._resolve_timezone()
        start_utc, end_utc = _today_range(tz_name)

        logger.info(
            "clear_memory debug: user_id=%s, range=[%s, %s), tz=%s",
            user_id, start_utc.isoformat(), end_utc.isoformat(), tz_name,
        )

        session = await db.get_latest_session_with_messages(
            user_id, start_utc, end_utc,
        )

        if session:
            messages = session.get("messages")
            # asyncpg 可能将 JSONB 返回为字符串，需要反序列化
            if isinstance(messages, str):
                messages = json.loads(messages)
            logger.info(
                "clear_memory debug: found session=%s, messages type=%s, len=%s",
                session.get("conversation_id"),
                type(messages).__name__,
                len(messages) if messages is not None else "N/A",
            )
            if messages:
                # 有消息 → 创建新会话
                new_id = uuid.uuid4().hex[:8]
                await db.create_session(user_id, new_id, "新会话")
                return {"cleared": True, "conversation_id": new_id}
            else:
                # 无消息 → 复用
                return {"cleared": True, "conversation_id": session["conversation_id"]}

        logger.info("clear_memory debug: no session found, creating new")
        # 无当天会话 → 创建新的
        new_id = uuid.uuid4().hex[:8]
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
