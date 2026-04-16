"""聊天服务 - 处理 SSE 流式响应"""

import json
from typing import AsyncGenerator

from src.config.settings import Config
from src.di.providers import create_chat_client


class ChatService:
    """聊天服务 - 处理 SSE 流式响应"""

    def __init__(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
        user_profile: dict | None = None,
    ) -> None:
        self.config = Config.load()
        self._client = None
        self.user_id = self._normalize_user_id(user_id)
        self.conversation_id = conversation_id or "default"
        self.user_profile = user_profile

    @staticmethod
    def _normalize_user_id(user_id: str | None) -> str | None:
        if user_id is None:
            return None
        normalized = user_id.strip()
        return normalized or None

    async def _ensure_user_memory_ready(self) -> None:
        if not self.user_id:
            return
        from src.db.memory import MemoryDB
        db = MemoryDB()
        await db.ensure_user_exists(self.user_id)

    async def _get_client(self):
        if self._client is None:
            await self._ensure_user_memory_ready()
            self._client = await create_chat_client(
                self.config,
                self.user_id,
                self.conversation_id,
                user_profile=self.user_profile,
            )
        return self._client

    async def chat_stream(self, user_input: str) -> AsyncGenerator[str, None]:
        """
        生成 SSE 事件流。

        Args:
            user_input: 用户输入

        Yields:
            SSE 格式的事件字符串
        """
        import logging
        logger = logging.getLogger(__name__)
        try:
            yield self._sse_event(
                "start",
                {"type": "start", "conversation_id": self.conversation_id},
            )
            client = await self._get_client()
            async for event in client.chat_stream_async(user_input):
                event_name = str(event.get("type", "delta"))
                yield self._sse_event(event_name, event)
        except Exception as exc:  # pragma: no cover - 由单测覆盖功能分支
            logger.exception(f"Chat stream error: {exc}")
            yield self._sse_event("error", {"type": "error", "message": str(exc)})

    def _sse_event(self, event_name: str, data: dict) -> str:
        """
        构建 SSE 事件格式字符串。

        Args:
            event_name: 事件名称
            data: 事件数据

        Returns:
            SSE 格式的事件字符串
        """
        return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
