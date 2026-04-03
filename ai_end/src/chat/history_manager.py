"""对话历史管理组件。"""

from __future__ import annotations

from typing import Any

from src.chat.prompts_runtime import TITLE_PROMPT_TEMPLATE
from src.config.settings import Config
from src.core.api_clients import get_llm_client
from src.core.api_queue import get_api_queue
from src.db.memory import MemoryDB


class HistoryManager:
    """负责会话历史加载、追加和标题生成。"""

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

    async def load(self) -> list[dict[str, Any]]:
        """读取会话历史。"""
        if not self.user_id:
            return []
        return await self.memory_db.get_conversation(self.user_id, self.conversation_id)

    async def append(self, messages: list[dict[str, Any]]) -> None:
        """追加会话消息。"""
        if not self.user_id:
            return
        await self.memory_db.append_conversation(
            self.user_id,
            messages,
            self.conversation_id,
        )

    async def generate_title(
        self,
        first_user_msg: str,
        first_assistant_msg: str,
    ) -> str:
        """生成并持久化会话标题。"""
        if not self.user_id:
            return "新会话"

        prompt = TITLE_PROMPT_TEMPLATE.format(
            first_user_msg=first_user_msg,
            first_assistant_msg=first_assistant_msg,
        )
        try:
            response = await self.api_queue.submit(
                "llm",
                self._completion_sync or self._create_title_completion_sync,
                prompt,
            )
        except Exception:
            return "新会话"

        title = (response.choices[0].message.content or "").strip()[:20]
        if not title:
            return "新会话"

        await self.memory_db.update_session_title(
            self.user_id,
            self.conversation_id,
            title,
        )
        return title

    def _create_title_completion_sync(self, prompt: str) -> Any:
        client = get_llm_client()
        return client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
        )
