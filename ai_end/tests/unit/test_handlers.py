"""
测试 src.chat.handlers - 消息处理函数

TDD RED 阶段：编写测试用例
"""
import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock

from src.chat.handlers import handle_tool_calls, handle_tool_calls_sync
from src.core.skill_parser import SkillInfo


class TestHandleToolCalls:
    """测试 handle_tool_calls 函数 - 使用同步包装器"""

    def test_sync_wrapper_submits_to_background_loop(self):
        """同步入口应统一提交到后台 loop，避免重复创建临时事件循环。"""
        mock_skill_system = Mock()
        expected = [{"role": "tool", "tool_call_id": "call_1", "content": "ok"}]
        fake_loop = Mock()

        def _fake_submit(coro, _loop):
            coro.close()
            fake_future = Mock()
            fake_future.result.return_value = expected
            return fake_future

        with patch("src.chat.handlers._get_tool_loop", return_value=fake_loop) as mock_get_tool_loop, patch(
            "src.chat.handlers.asyncio.run_coroutine_threadsafe",
            side_effect=_fake_submit,
        ) as mock_submit:
            result = handle_tool_calls_sync([], mock_skill_system)

        assert result == expected
        mock_get_tool_loop.assert_called_once_with()
        mock_submit.assert_called_once()

    def test_handle_single_tool_call(self):
        """测试处理单个工具调用"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {"test": True}  # 添加技能到 available_skills
        mock_skill_system.get_skill_content.return_value = "test skill content"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "call_skill_test"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        mock_tool_call.id = "call_123"

        # Act
        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system)

        # Assert
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_123"
        assert result[0]["content"] == "test skill content"

    def test_handle_multiple_tool_calls(self):
        """测试处理多个工具调用"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {"first": True, "second": True}
        mock_skill_system.get_skill_content.side_effect = [
            "first skill content",
            "second skill content"
        ]

        mock_tool_call_1 = Mock()
        mock_tool_call_1.function.name = "call_skill_first"
        mock_tool_call_1.function.arguments = '{}'
        mock_tool_call_1.id = "call_1"

        mock_tool_call_2 = Mock()
        mock_tool_call_2.function.name = "call_skill_second"
        mock_tool_call_2.function.arguments = '{}'
        mock_tool_call_2.id = "call_2"

        # Act
        result = handle_tool_calls_sync([mock_tool_call_1, mock_tool_call_2], mock_skill_system)

        # Assert
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == "first skill content"
        assert result[1]["tool_call_id"] == "call_2"
        assert result[1]["content"] == "second skill content"

    def test_handle_empty_tool_calls(self):
        """测试处理空工具调用列表"""
        # Arrange
        mock_skill_system = Mock()

        # Act
        result = handle_tool_calls_sync([], mock_skill_system)

        # Assert
        assert result == []
        mock_skill_system.get_skill_content.assert_not_called()

    def test_strips_call_skill_prefix(self):
        """测试正确去除 call_skill_ 前缀"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {"general-assessment": True}
        mock_skill_system.get_skill_content.return_value = "skill content"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "call_skill_general-assessment"
        mock_tool_call.function.arguments = '{}'
        mock_tool_call.id = "call_123"

        # Act
        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system)

        # Assert
        # 验证调用时使用了去除前缀的技能名
        mock_skill_system.get_skill_content.assert_called_once_with("general-assessment")
        assert result[0]["content"] == "skill content"

    def test_nonexistent_skill_returns_empty_content(self):
        """测试不存在的技能返回错误信息（新逻辑：未找到或未激活）"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {}  # 不包含 "nonexistent"
        mock_skill_system.get_skill_content.return_value = ""

        mock_tool_call = Mock()
        mock_tool_call.function.name = "call_skill_nonexistent"
        mock_tool_call.function.arguments = '{}'
        mock_tool_call.id = "call_123"

        # Act
        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system)

        # Assert - 新逻辑：返回错误信息
        assert "error" in result[0]["content"]
        assert "未找到或未激活" in result[0]["content"]

    def test_handle_read_reference_call(self):
        """测试处理 read_reference 工具调用"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "general-assessment": SkillInfo(
                name="general-assessment",
                description="通用评估",
                content="",
                verification_token="",
                metadata={"read_reference_parent": True},
            )
        }
        mock_skill_system.read_reference.return_value = "# Reference Content\nThis is reference content."

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name": "test-skill", "file_path": "references/test.md"}'
        mock_tool_call.id = "call_456"

        # Act
        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"general-assessment"})

        # Assert
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_456"
        assert "# Reference Content" in result[0]["content"]
        mock_skill_system.read_reference.assert_called_once_with("test-skill", "references/test.md", "")

    def test_handle_read_reference_with_missing_args(self):
        """测试 read_reference 调用缺少参数"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "general-assessment": SkillInfo(
                name="general-assessment",
                description="通用评估",
                content="",
                verification_token="",
                metadata={"read_reference_parent": True},
            )
        }
        mock_skill_system.read_reference.return_value = "错误：缺少参数"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name": "test-skill"}'  # 缺少 file_path
        mock_tool_call.id = "call_789"

        # Act
        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"general-assessment"})

        # Assert
        assert len(result) == 1
        mock_skill_system.read_reference.assert_called_once_with("test-skill", "", "")

    def test_handle_read_reference_with_lines_param(self):
        """测试 read_reference 支持 lines 参数指定行范围"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "general-assessment": SkillInfo(
                name="general-assessment",
                description="通用评估",
                content="",
                verification_token="",
                metadata={"read_reference_parent": True},
            )
        }
        # lines 参数返回指定行范围的内容
        mock_skill_system.read_reference.return_value = "Line 5\nLine 6\nLine 7"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name": "test", "file_path": "refs/test.md", "lines": "5-7"}'
        mock_tool_call.id = "call_lines_1"

        # Act
        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"general-assessment"})

        # Assert
        assert len(result) == 1
        assert "Line 5" in result[0]["content"]
        mock_skill_system.read_reference.assert_called_once_with("test", "refs/test.md", "5-7")

    def test_handle_mixed_tool_calls(self):
        """测试处理混合的工具调用（技能 + read_reference）"""
        # Arrange
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "general-assessment": SkillInfo(
                name="general-assessment",
                description="通用评估",
                content="",
                verification_token="",
                metadata={"read_reference_parent": True},
            ),
            "test-skill": SkillInfo(
                name="test-skill",
                description="测试技能",
                content="",
                verification_token="",
            ),
        }
        mock_skill_system.get_skill_content.return_value = "skill content"
        mock_skill_system.read_reference.return_value = "reference content"

        # 技能调用
        mock_tool_call_1 = Mock()
        mock_tool_call_1.function.name = "test-skill"
        mock_tool_call_1.function.arguments = '{}'
        mock_tool_call_1.id = "call_1"

        # read_reference 调用
        mock_tool_call_2 = Mock()
        mock_tool_call_2.function.name = "read_reference"
        mock_tool_call_2.function.arguments = '{"skill_name": "test", "file_path": "refs/test.md"}'
        mock_tool_call_2.id = "call_2"

        # Act
        result = handle_tool_calls_sync(
            [mock_tool_call_1, mock_tool_call_2],
            mock_skill_system,
            {"general-assessment"},
        )

        # Assert
        assert len(result) == 2
        assert result[0]["content"] == "skill content"
        assert result[1]["content"] == "reference content"
        mock_skill_system.get_skill_content.assert_called_once_with("test-skill")
        mock_skill_system.read_reference.assert_called_once_with("test", "refs/test.md", "")

    def test_sync_wrapper_reuses_same_event_loop_for_secondary_tools(self):
        """连续调用同步包装器时，应复用同一个事件循环以避免 asyncpg 连接池跨循环问题"""
        import json

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "policy-retrieval": Mock(
                secondary_tools=[
                    {"name": "search_articles", "handler": "article_retrieval.search_articles"}
                ]
            )
        }

        mock_tool_call = Mock()
        mock_tool_call.function.name = "search_articles"
        mock_tool_call.function.arguments = '{"query": "规培"}'
        mock_tool_call.id = "call_001"

        async def _fake_dispatch(*args, **kwargs):
            return json.dumps({"loop_id": id(asyncio.get_running_loop())})

        with patch("src.chat.handlers._dispatch_secondary_tool", new=AsyncMock(side_effect=_fake_dispatch)):
            first = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"policy-retrieval"})
            second = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"policy-retrieval"})

        first_loop_id = json.loads(first[0]["content"])["loop_id"]
        second_loop_id = json.loads(second[0]["content"])["loop_id"]
        assert first_loop_id == second_loop_id

    @pytest.mark.asyncio
    async def test_handle_read_reference_call_with_async_skill_system(self):
        """当 skill_system.read_reference 为异步函数时，应该被正确 await 并返回字符串内容。"""

        class _AsyncSkillSystem:
            def __init__(self) -> None:
                self.available_skills = {
                    "general-assessment": SkillInfo(
                        name="general-assessment",
                        description="通用评估",
                        content="",
                        verification_token="",
                        metadata={"read_reference_parent": True},
                    )
                }
                self.called_with = None

            async def read_reference(self, skill_name: str, file_path: str, lines: str = "") -> str:
                self.called_with = (skill_name, file_path, lines)
                return "async reference content"

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name":"db-skill","file_path":"references/a.md"}'
        mock_tool_call.id = "call_async_1"

        skill_system = _AsyncSkillSystem()
        result = await handle_tool_calls([mock_tool_call], skill_system, {"general-assessment"})  # type: ignore[arg-type]

        assert result[0]["content"] == "async reference content"
        assert skill_system.called_with == ("db-skill", "references/a.md", "")

    def test_handle_tool_calls_applies_read_reference_truncation(self):
        """read_reference 通过 handle_tool_calls 时应应用截断策略。"""
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "general-assessment": SkillInfo(
                name="general-assessment",
                description="通用评估",
                content="",
                verification_token="",
                metadata={"read_reference_parent": True},
            )
        }
        mock_skill_system.read_reference.return_value = "内容 " * 3000  # >5000 字符

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name":"s","file_path":"references/a.md"}'
        mock_tool_call.id = "call_rr_1"

        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"general-assessment"})
        assert "截断提示" in result[0]["content"]

    def test_handle_read_reference_call_without_activation(self):
        """未激活指导技能时，read_reference 应返回未激活错误。"""
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {}

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name":"s","file_path":"references/a.md"}'
        mock_tool_call.id = "call_rr_blocked"

        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system)
        assert "未激活" in result[0]["content"]
        mock_skill_system.read_reference.assert_not_called()

    def test_handle_read_reference_call_with_non_guidance_activation(self):
        """仅激活非指导技能时，read_reference 仍应返回未激活错误。"""
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "article-retrieval": Mock(),
        }

        mock_tool_call = Mock()
        mock_tool_call.function.name = "read_reference"
        mock_tool_call.function.arguments = '{"skill_name":"s","file_path":"references/a.md"}'
        mock_tool_call.id = "call_rr_non_guidance"

        result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"article-retrieval"})
        assert "未激活" in result[0]["content"]
        mock_skill_system.read_reference.assert_not_called()

    def test_handle_tool_calls_applies_search_articles_truncation(self):
        """search_articles 通过 handle_tool_calls 时应按配置限制结果数量。"""
        from src.chat.context_truncator import _SEARCH_DOCUMENTS_MAX_RESULTS

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "policy-retrieval": Mock(
                secondary_tools=[
                    {"name": "search_articles", "handler": "article_retrieval.search_articles"}
                ]
            )
        }

        mock_tool_call = Mock()
        mock_tool_call.function.name = "search_articles"
        mock_tool_call.function.arguments = '{"query":"规培"}'
        mock_tool_call.id = "call_sp_1"

        payload = {
            "results": [
                {"id": i, "title": f"t{i}", "summary": "很长摘要" * 80, "score": 0.9}
                for i in range(1, _SEARCH_DOCUMENTS_MAX_RESULTS + 4)
            ]
        }

        with patch("src.chat.handlers._dispatch_secondary_tool", new=AsyncMock(return_value=json.dumps(payload, ensure_ascii=False))):
            result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"policy-retrieval"})

        data = json.loads(result[0]["content"])
        assert len(data["results"]) <= _SEARCH_DOCUMENTS_MAX_RESULTS
        assert "_meta" in data

    def test_handle_tool_calls_applies_grep_article_truncation(self):
        """grep_article 通过 handle_tool_calls 时应保留 title 且限制匹配数。"""
        mock_skill_system = Mock()
        mock_skill_system.available_skills = {
            "policy-retrieval": Mock(
                secondary_tools=[
                    {"name": "grep_article", "handler": "article_retrieval.grep_article"}
                ]
            )
        }

        mock_tool_call = Mock()
        mock_tool_call.function.name = "grep_article"
        mock_tool_call.function.arguments = '{"policy_id":1,"keyword":"服务期"}'
        mock_tool_call.id = "call_gp_1"

        payload = {
            "status": "success",
            "data": {
                "title": "政策标题",
                "matches": [{"content": "内容" * 300, "line_number": i} for i in range(1, 10)],
            },
            "metadata": {"total_matches": 9},
        }

        with patch("src.chat.handlers._dispatch_secondary_tool", new=AsyncMock(return_value=json.dumps(payload, ensure_ascii=False))):
            result = handle_tool_calls_sync([mock_tool_call], mock_skill_system, {"policy-retrieval"})

        data = json.loads(result[0]["content"])
        assert data["data"]["title"] == "政策标题"
        assert len(data["data"]["matches"]) <= 3


class TestContextTruncator:
    """测试工具输出智能截断（方案 B）"""

    def test_skill_content_not_truncated(self):
        """技能内容不应该被截断（通常较小且高价值）。"""
        from src.chat.context_truncator import truncate_tool_output

        skill_content = "这是技能内容，通常不会太长。" * 10  # 约 200 字符
        result = truncate_tool_output("skill", "test-skill", skill_content)

        # 技能内容不应被截断
        assert result["content"] == skill_content
        assert result["truncated"] is False

    def test_read_reference_truncates_by_paragraph_boundary(self):
        """read_reference 应按段落边界截断，保留首尾。"""
        from src.chat.context_truncator import truncate_tool_output

        # 构造包含多个段落的长内容（超过 5000 字符阈值）
        long_content = ""
        for i in range(100):  # 100 个段落
            chapter_num = i + 1
            long_content += f"## 第{chapter_num}章\n这是第{chapter_num}章的内容。" + "额外内容。" * 20 + "\n\n"

        # 确保内容足够长
        assert len(long_content) > 5000, f"测试内容太短: {len(long_content)} 字符"

        result = truncate_tool_output("read_reference", "test-skill", long_content)

        # 应该被截断
        assert result["truncated"] is True
        assert len(result["content"]) < len(long_content)

        # 应该包含截断提示
        assert "省略" in result["content"] or "..." in result["content"] or "章节" in result["content"]
        assert result["original_size"] == len(long_content)

    def test_search_documents_limits_to_top3_and_summary_length(self):
        """search_documents 应按配置限制返回数量和摘要长度。"""
        from src.chat.context_truncator import truncate_search_documents_result
        from src.chat.context_truncator import _SEARCH_DOCUMENTS_MAX_RESULTS

        # 构造超过限制数量的响应
        results = []
        for i in range(_SEARCH_DOCUMENTS_MAX_RESULTS + 3):
            results.append({
                "id": i + 1,
                "title": f"政策标题 {i+1}",
                "summary": "这是一个很长的政策摘要，" * 20,  # 约 300 字符
                "score": 0.9 - i * 0.05
            })

        response = {"results": results}
        result = truncate_search_documents_result(response)

        # 应该只返回前 N 条（N 由配置决定）
        assert len(result["results"]) <= _SEARCH_DOCUMENTS_MAX_RESULTS
        assert "_meta" in result
        # 每条的摘要应该被限制（200 + "..." = 203）
        for item in result["results"]:
            assert len(item.get("summary", "")) <= 203

    def test_grep_document_limits_matches_and_content_length(self):
        """grep_document 应限制匹配数量和每条内容长度。"""
        from src.chat.context_truncator import truncate_grep_document_result

        # 构造包含 10 条匹配的响应
        matches = []
        for i in range(10):
            matches.append({
                "content": f"匹配内容 {i+1}：" + "很长的内容段。" * 50,
                "line_number": i * 10 + 1
            })

        response = {"status": "success", "data": {"matches": matches}}
        result = truncate_grep_document_result(response)

        # 应该只返回前 3 条
        assert len(result["data"]["matches"]) <= 3
        # 每条的内容应该被限制
        for match in result["data"]["matches"]:
            assert len(match.get("content", "")) <= 500

    def test_truncation_adds_requery_hint(self):
        """截断后应添加提示用户可以重新查询。"""
        from src.chat.context_truncator import truncate_tool_output

        long_content = "内容 " * 2000  # 远超限制
        result = truncate_tool_output("read_reference", "test", long_content)

        assert "提示" in result["content"] or "查询" in result["content"]
        assert result["truncated"] is True

    def test_truncate_generic_tool_output(self):
        """未知类型的工具输出应有统一截断策略。"""
        from src.chat.context_truncator import truncate_tool_output

        long_output = "x" * 5000
        result = truncate_tool_output("unknown_tool", "test", long_output)

        assert result["truncated"] is True
        assert len(result["content"]) < len(long_output)
        assert result["original_size"] == 5000

    def test_read_reference_truncation_respects_hard_limit(self):
        """read_reference 截断后的总长度必须不超过 max_chars 硬上限（bug 修复）。"""
        from src.chat.context_truncator import truncate_tool_output, _READ_REFERENCE_MAX_CHARS

        # 构造一个只有2个段落的长内容，会触发"段落少直接硬截断"逻辑
        long_content = "## 第一章\n" + "内容" * 6000 + "\n\n## 第二章\n" + "更多内容" * 1000
        assert len(long_content) > _READ_REFERENCE_MAX_CHARS

        result = truncate_tool_output("read_reference", "test", long_content)

        # 断言：最终返回的内容长度必须 <= max_chars（硬上限）
        assert len(result["content"]) <= _READ_REFERENCE_MAX_CHARS, \
            f"返回内容长度 {len(result['content'])} 超过硬上限 {_READ_REFERENCE_MAX_CHARS}"
        assert result["truncated"] is True
        assert result["returned_size"] == len(result["content"]), \
            "returned_size 应该等于实际返回内容的长度"

    def test_read_reference_truncation_with_many_paragraphs_respects_hard_limit(self):
        """read_reference 多段落截断后的总长度也必须不超过硬上限。"""
        from src.chat.context_truncator import truncate_tool_output, _READ_REFERENCE_MAX_CHARS

        # 构造包含很多段落的长内容
        long_content = ""
        for i in range(50):
            long_content += f"## 第{i+1}章\n" + "章节内容" * 200 + "\n\n"

        result = truncate_tool_output("read_reference", "test", long_content)

        # 断言：最终返回的内容长度必须 <= max_chars
        assert len(result["content"]) <= _READ_REFERENCE_MAX_CHARS, \
            f"返回内容长度 {len(result['content'])} 超过硬上限 {_READ_REFERENCE_MAX_CHARS}"
        assert result["truncated"] is True


class TestHandleFormMemoryUnified:
    """测试 handle_form_memory 通过 MemoryManager 统一入口调用"""

    @pytest.mark.asyncio
    async def test_handle_form_memory_calls_memory_manager(self):
        """handle_form_memory 应委托给 MemoryManager.form_memory，不再独立调用 LLM。"""
        from unittest.mock import AsyncMock, patch, MagicMock

        mock_db = MagicMock()
        mock_db.get_conversation = AsyncMock(return_value=[
            {"role": "user", "content": "测试消息"},
        ])

        fake_result = {
            "saved": True,
            "attempts_used": 1,
            "last_error": "",
            "skip_reason": "",
            "portrait_text": '{"confirmed":{"identity":[],"interests":[],"constraints":["北京"]},"hypothesized":{"identity":[],"interests":[]}}',
            "knowledge_text": '{"confirmed_facts":["已确认"],"pending_queries":[]}',
        }

        with patch("src.db.memory.MemoryDB", return_value=mock_db), \
             patch("src.chat.memory_manager.MemoryManager") as MockMM:
            mock_manager = MagicMock()
            mock_manager.form_memory = AsyncMock(return_value=fake_result)
            MockMM.return_value = mock_manager

            from src.chat.handlers import handle_form_memory
            result = await handle_form_memory(user_id="u1", conversation_id="c1")

            # 验证委托给 MemoryManager
            mock_manager.form_memory.assert_awaited_once()
            assert "记忆已形成" in result
            assert fake_result["portrait_text"] in result

    @pytest.mark.asyncio
    async def test_handle_form_memory_returns_success_text(self):
        """saved=True 时返回包含画像和知识的文本。"""
        from unittest.mock import AsyncMock, patch, MagicMock

        mock_db = MagicMock()
        mock_db.get_conversation = AsyncMock(return_value=[
            {"role": "user", "content": "我想去北京读内科"},
        ])

        fake_result = {
            "saved": True,
            "attempts_used": 1,
            "last_error": "",
            "skip_reason": "",
            "portrait_text": '{"confirmed":{"identity":[],"interests":[],"constraints":["北京"]}}',
            "knowledge_text": '{"confirmed_facts":[],"pending_queries":["分数线"]}',
        }

        with patch("src.db.memory.MemoryDB", return_value=mock_db), \
             patch("src.chat.memory_manager.MemoryManager") as MockMM:
            mock_manager = MagicMock()
            mock_manager.form_memory = AsyncMock(return_value=fake_result)
            MockMM.return_value = mock_manager

            from src.chat.handlers import handle_form_memory
            result = await handle_form_memory(user_id="u1", conversation_id="c1")

            assert "记忆已形成" in result
            assert "用户画像" in result
            assert "知识记忆" in result
            assert fake_result["portrait_text"] in result
            assert fake_result["knowledge_text"] in result

    @pytest.mark.asyncio
    async def test_handle_form_memory_returns_failure_text(self):
        """saved=False 时返回包含重试次数和错误原因的失败文案。"""
        from unittest.mock import AsyncMock, patch, MagicMock

        mock_db = MagicMock()
        mock_db.get_conversation = AsyncMock(return_value=[
            {"role": "user", "content": "测试"},
        ])

        fake_result = {
            "saved": False,
            "attempts_used": 3,
            "last_error": "第3次尝试: 无法解析",
            "skip_reason": "max_retries_exceeded",
            "portrait_text": "",
            "knowledge_text": "",
        }

        with patch("src.db.memory.MemoryDB", return_value=mock_db), \
             patch("src.chat.memory_manager.MemoryManager") as MockMM:
            mock_manager = MagicMock()
            mock_manager.form_memory = AsyncMock(return_value=fake_result)
            MockMM.return_value = mock_manager

            from src.chat.handlers import handle_form_memory
            result = await handle_form_memory(user_id="u1", conversation_id="c1")

            assert "记忆形成失败" in result
            assert "3" in result  # 重试次数
            assert "无法解析" in result  # 错误原因

    @pytest.mark.asyncio
    async def test_handle_form_memory_passes_correct_params_to_manager(self):
        """handle_form_memory 应将 user_id 和 conversation_id 传递给 MemoryManager。"""
        from unittest.mock import AsyncMock, patch, MagicMock

        mock_db = MagicMock()
        mock_db.get_conversation = AsyncMock(return_value=[
            {"role": "user", "content": "测试"},
        ])

        fake_result = {
            "saved": True, "attempts_used": 1, "last_error": "",
            "skip_reason": "", "portrait_text": "{}", "knowledge_text": "{}",
        }

        with patch("src.db.memory.MemoryDB", return_value=mock_db), \
             patch("src.chat.memory_manager.MemoryManager") as MockMM:
            mock_manager = MagicMock()
            mock_manager.form_memory = AsyncMock(return_value=fake_result)
            MockMM.return_value = mock_manager

            from src.chat.handlers import handle_form_memory
            await handle_form_memory(user_id="test_uid", conversation_id="test_cid")

            MockMM.assert_called_once_with(
                user_id="test_uid",
                conversation_id="test_cid",
                memory_db=mock_db,
            )


class TestHandleFormMemory:
    """测试 handle_form_memory 函数 — 基础行为"""

    def test_form_memory_delegates_to_memory_manager(self):
        """验证 handlers.py 通过 MemoryManager 统一入口处理记忆，而非独立解析。"""
        import inspect
        from src.chat import handlers

        source = inspect.getsource(handlers.handle_form_memory)

        # 验证使用了 MemoryManager
        assert "MemoryManager" in source, \
            "handle_form_memory 应使用 MemoryManager 统一入口"

        # 验证不再直接导入 openai
        assert "OpenAI" not in source, \
            "handle_form_memory 不应直接创建 OpenAI 客户端"

    @pytest.mark.asyncio
    async def test_form_memory_no_user_returns_error(self):
        """无 user_id 时应返回错误提示。"""
        from src.chat.handlers import handle_form_memory
        result = await handle_form_memory(user_id=None)
        assert "用户ID" in result


class TestFormMemoryDeferredExecution:
    """测试 form_memory tool_call 延迟到回合末执行（触发层与执行层分离）"""

    @pytest.mark.asyncio
    async def test_form_memory_tool_only_registers_after_turn_flag(self):
        """form_memory 被调用时应只通过回调登记，不直接调用 handle_form_memory。"""
        marked = {"value": False}

        def mark():
            marked["value"] = True

        # 构造 form_memory tool_call
        mock_tool_call = Mock()
        mock_tool_call.function.name = "form_memory"
        mock_tool_call.function.arguments = '{"reason": "用户提到了偏好"}'
        mock_tool_call.id = "call_fm_1"

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {}

        with patch("src.chat.handlers.handle_form_memory") as mock_handle_fm:
            result = await handle_tool_calls(
                [mock_tool_call],
                mock_skill_system,
                activated_skills=set(),
                mark_form_memory_after_turn=mark,
            )

        # 断言：回调被调用
        assert marked["value"] is True
        # 断言：handle_form_memory 未被调用（不直接执行）
        mock_handle_fm.assert_not_called()
        # 断言：返回登记成功文案
        assert "登记" in result[0]["content"] or "回合末" in result[0]["content"]

    @pytest.mark.asyncio
    async def test_form_memory_without_callback_falls_back_to_direct_execution(self):
        """不传 mark_form_memory_after_turn 回调时，仍走原有直接执行路径。"""
        mock_tool_call = Mock()
        mock_tool_call.function.name = "form_memory"
        mock_tool_call.function.arguments = '{"reason": "测试"}'
        mock_tool_call.id = "call_fm_2"

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {}

        with patch("src.chat.handlers.handle_form_memory", new_callable=AsyncMock, return_value="记忆已形成") as mock_handle_fm:
            result = await handle_tool_calls(
                [mock_tool_call],
                mock_skill_system,
                activated_skills=set(),
            )

        # 断言：handle_form_memory 被直接调用
        mock_handle_fm.assert_called_once()
        assert result[0]["content"] == "记忆已形成"

    @pytest.mark.asyncio
    async def test_form_memory_callback_receives_no_arguments(self):
        """回调应为无参 Callable[[], None]，不需要接收 reason 等参数。"""
        call_log = []

        def mark():
            call_log.append("called")

        mock_tool_call = Mock()
        mock_tool_call.function.name = "form_memory"
        mock_tool_call.function.arguments = '{"reason": "用户说喜欢北京"}'
        mock_tool_call.id = "call_fm_3"

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {}

        with patch("src.chat.handlers.handle_form_memory"):
            result = await handle_tool_calls(
                [mock_tool_call],
                mock_skill_system,
                activated_skills=set(),
                mark_form_memory_after_turn=mark,
            )

        # 断言：回调恰好被调用一次
        assert call_log == ["called"]

    def test_sync_wrapper_passes_through_mark_form_memory_callback(self):
        """handle_tool_calls_sync 应透传 mark_form_memory_after_turn 参数。"""
        marked = {"value": False}

        def mark():
            marked["value"] = True

        mock_tool_call = Mock()
        mock_tool_call.function.name = "form_memory"
        mock_tool_call.function.arguments = '{"reason": "测试同步透传"}'
        mock_tool_call.id = "call_fm_sync_1"

        mock_skill_system = Mock()
        mock_skill_system.available_skills = {}

        expected = [{"role": "tool", "tool_call_id": "call_fm_sync_1", "content": "已登记，将在回合末执行记忆形成。"}]
        fake_loop = Mock()

        def _fake_submit(coro, _loop):
            coro.close()
            fake_future = Mock()
            fake_future.result.return_value = expected
            return fake_future

        with patch("src.chat.handlers._get_tool_loop", return_value=fake_loop), \
             patch("src.chat.handlers.asyncio.run_coroutine_threadsafe", side_effect=_fake_submit) as mock_submit:
            result = handle_tool_calls_sync(
                [mock_tool_call],
                mock_skill_system,
                mark_form_memory_after_turn=mark,
            )

        # 验证 run_coroutine_threadsafe 被调用
        mock_submit.assert_called_once()
        assert result == expected
