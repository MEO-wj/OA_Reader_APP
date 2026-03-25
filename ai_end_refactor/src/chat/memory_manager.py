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

    async def form_memory(self, messages: list[dict[str, Any]]) -> dict[str, str]:
        """形成用户画像与知识记忆。"""
        if not self.user_id:
            return {"portrait": "", "knowledge": ""}

        prompt = self._build_memory_prompt(messages)
        response = await self.api_queue.submit(
            "llm",
            self._completion_sync or self._create_memory_completion_sync,
            prompt,
        )
        content = _sanitize_memory_text(response.choices[0].message.content or "")
        result = self._parse_memory(content)
        await self.memory_db.save_profile(
            self.user_id,
            result["portrait"],
            result["knowledge"],
        )
        return result

    def _build_memory_prompt(self, messages: list[dict[str, Any]]) -> str:
        conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return MEMORY_PROMPT_TEMPLATE.format(conversation=conversation)

    def _create_memory_completion_sync(self, prompt: str) -> Any:
        client = get_llm_client()
        return client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )

    def _parse_memory(self, content: str) -> dict[str, str]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {"portrait": "", "knowledge": ""}

        portrait = json.dumps(
            {
                "hard_constraints": data.get("hard_constraints", []),
                "soft_constraints": data.get("soft_constraints", []),
                "risk_tolerance": data.get("risk_tolerance", []),
            },
            ensure_ascii=False,
        )
        knowledge = json.dumps(
            {
                "verified_facts": data.get("verified_facts", []),
                "pending_queries": data.get("pending_queries", []),
            },
            ensure_ascii=False,
        )
        return {"portrait": portrait, "knowledge": knowledge}
