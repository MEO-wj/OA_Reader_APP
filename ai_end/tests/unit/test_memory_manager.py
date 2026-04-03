"""TDD: 记忆管理器单元测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.chat.memory_manager import MemoryManager
from src.chat.prompts_runtime import MEMORY_PROMPT_TEMPLATE


class TestMemoryManager:
    """MemoryManager 测试套件。"""

    @pytest.mark.asyncio
    async def test_form_memory_returns_empty_when_no_user(self):
        """未提供用户时应跳过记忆形成。"""
        manager = MemoryManager()

        result = await manager.form_memory([{"role": "user", "content": "你好"}])

        assert result == {"portrait": "", "knowledge": ""}

    @pytest.mark.asyncio
    async def test_form_memory_calls_queue_and_save_profile(self):
        """应调用 LLM 队列并保存画像。"""
        queue = MagicMock()
        queue.submit = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"hard_constraints":["北京"],"soft_constraints":["内科"],"risk_tolerance":[],"verified_facts":["已确认"],"pending_queries":["待查"]}'
                        )
                    )
                ]
            )
        )

        db = MagicMock()
        db.save_profile = AsyncMock()

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(
                user_id="user-1",
                conversation_id="conv-1",
                memory_db=db,
            )
            result = await manager.form_memory([{"role": "user", "content": "我想去北京读内科"}])

        queue.submit.assert_awaited_once()
        db.save_profile.assert_awaited_once()
        assert "北京" in result["portrait"]
        assert "已确认" in result["knowledge"]

    def test_create_memory_completion_sync_uses_shared_llm_client(self):
        """记忆生成应复用统一 LLM client，而不是自行创建 OpenAI 实例。"""
        from src.config import Config

        shared_client = MagicMock()
        manager = MemoryManager(config=Config.with_defaults())

        with patch("src.chat.memory_manager.get_llm_client", return_value=shared_client) as mock_get_llm_client:
            manager._create_memory_completion_sync("生成记忆")

        mock_get_llm_client.assert_called_once()
        shared_client.chat.completions.create.assert_called_once()

    def test_memory_prompt_uses_runtime_template(self):
        """验证 memory_manager.py 源码中使用了 MEMORY_PROMPT_TEMPLATE。"""
        import inspect
        from src.chat import memory_manager

        # 获取源码
        source = inspect.getsource(memory_manager)

        # 验证导入了 MEMORY_PROMPT_TEMPLATE
        assert "from src.chat.prompts_runtime import MEMORY_PROMPT_TEMPLATE" in source, \
            "memory_manager.py 应从 prompts_runtime 导入 MEMORY_PROMPT_TEMPLATE"

        # 验证 _build_memory_prompt 使用了模板
        assert "MEMORY_PROMPT_TEMPLATE" in source, \
            "memory_manager.py 应使用 MEMORY_PROMPT_TEMPLATE"

        # 验证 _build_memory_prompt 方法体
        method_source = inspect.getsource(memory_manager.MemoryManager._build_memory_prompt)
        assert "MEMORY_PROMPT_TEMPLATE.format" in method_source, \
            "_build_memory_prompt 应调用 MEMORY_PROMPT_TEMPLATE.format()"