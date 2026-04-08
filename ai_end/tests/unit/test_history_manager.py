"""TDD: 对话历史管理器单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.chat.history_manager import HistoryManager
from src.chat.prompts_runtime import TITLE_PROMPT_TEMPLATE


class TestHistoryManager:
    """HistoryManager 测试套件。"""

    @pytest.mark.asyncio
    async def test_load_returns_empty_when_no_user(self):
        """未提供用户时应返回空历史。"""
        manager = HistoryManager()

        history = await manager.load()

        assert history == []

    @pytest.mark.asyncio
    async def test_load_and_append_use_memory_db(self):
        """应通过 MemoryDB 读写会话历史。"""
        uid_a = "00000000-0000-0000-0007-000000000001"
        db = MagicMock()
        db.get_conversation = AsyncMock(return_value=[{"role": "user", "content": "hello"}])
        db.append_conversation = AsyncMock()

        manager = HistoryManager(user_id=uid_a, conversation_id="conv-1", memory_db=db)
        history = await manager.load()
        await manager.append([{"role": "assistant", "content": "world"}])

        db.get_conversation.assert_awaited_once_with(uid_a, "conv-1")
        db.append_conversation.assert_awaited_once_with(
            uid_a,
            [{"role": "assistant", "content": "world"}],
            "conv-1",
        )
        assert history == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_generate_title_uses_queue_and_updates_db(self):
        """应生成标题并回写到会话表。"""
        uid_a = "00000000-0000-0000-0007-000000000001"
        queue = MagicMock()
        queue.submit = AsyncMock(
            return_value=MagicMock(
                choices=[MagicMock(message=MagicMock(content="内科考研规划"))]
            )
        )

        db = MagicMock()
        db.update_session_title = AsyncMock()

        with patch("src.chat.history_manager.get_api_queue", return_value=queue), patch(
            "src.chat.history_manager.MemoryDB",
            return_value=db,
        ):
            manager = HistoryManager(user_id=uid_a, conversation_id="conv-1")
            title = await manager.generate_title("我想考内科研究生", "先明确城市和院校层次")

        assert title == "内科考研规划"
        db.update_session_title.assert_awaited_once_with(uid_a, "conv-1", "内科考研规划")

    def test_create_title_completion_sync_uses_shared_llm_client(self):
        """标题生成应复用统一 LLM client，而不是自行创建 OpenAI 实例。"""
        from src.config import Config

        shared_client = MagicMock()
        manager = HistoryManager(config=Config.with_defaults())

        with patch("src.chat.history_manager.get_llm_client", return_value=shared_client) as mock_get_llm_client:
            manager._create_title_completion_sync("生成标题")

        mock_get_llm_client.assert_called_once()
        shared_client.chat.completions.create.assert_called_once()

    def test_title_prompt_uses_runtime_template(self):
        """验证 history_manager.py 源码中使用了 TITLE_PROMPT_TEMPLATE。"""
        import inspect
        from src.chat import history_manager

        # 获取源码
        source = inspect.getsource(history_manager)

        # 验证导入了 TITLE_PROMPT_TEMPLATE
        assert "from src.chat.prompts_runtime import TITLE_PROMPT_TEMPLATE" in source, \
            "history_manager.py 应从 prompts_runtime 导入 TITLE_PROMPT_TEMPLATE"

        # 验证 generate_title 使用了模板
        assert "TITLE_PROMPT_TEMPLATE" in source, \
            "history_manager.py 应使用 TITLE_PROMPT_TEMPLATE"

        # 验证 generate_title 方法体
        method_source = inspect.getsource(history_manager.HistoryManager.generate_title)
        assert "TITLE_PROMPT_TEMPLATE.format" in method_source, \
            "generate_title 应调用 TITLE_PROMPT_TEMPLATE.format()"