"""TDD: 记忆管理器单元测试。"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.chat.memory_manager import MemoryManager
from src.chat.prompts_runtime import MEMORY_PROMPT_TEMPLATE


class TestMemoryManagerV2ReturnContract:
    """MemoryManager.form_memory v2 结构化返回契约测试。"""

    @pytest.mark.asyncio
    async def test_return_has_all_required_fields(self):
        """form_memory 返回结构体应包含所有 v2 契约字段。"""
        uid = "00000000-0000-0000-0008-000000000099"
        queue = MagicMock()
        queue.submit = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"confirmed":{"identity":[],"interests":[],"constraints":[]},"hypothesized":{"identity":[],"interests":[]},"knowledge":{"confirmed_facts":[],"pending_queries":[]}}'
                        )
                    )
                ]
            )
        )
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory([{"role": "user", "content": "你好"}])

        # 验证 v2 契约字段全部存在
        required_fields = {"saved", "attempts_used", "last_error", "skip_reason", "portrait_text", "knowledge_text"}
        assert required_fields.issubset(result.keys()), f"缺少字段: {required_fields - result.keys()}"

    @pytest.mark.asyncio
    async def test_saved_true_on_success(self):
        """成功保存时 saved=True，skip_reason 为空。"""
        uid = "00000000-0000-0000-0008-000000000100"
        queue = MagicMock()
        queue.submit = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"confirmed":{"identity":["大三"],"interests":["编程"],"constraints":["广州"]},"hypothesized":{"identity":[],"interests":[]},"knowledge":{"confirmed_facts":["已确认"],"pending_queries":["待查"]}}'
                        )
                    )
                ]
            )
        )
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory([{"role": "user", "content": "你好"}])

        assert result["saved"] is True
        assert result["skip_reason"] == ""
        assert result["attempts_used"] >= 1
        assert result["last_error"] == ""

    @pytest.mark.asyncio
    async def test_skip_when_no_user_id(self):
        """user_id 为空时 saved=False，skip_reason=no_user_id。"""
        manager = MemoryManager()

        result = await manager.form_memory([{"role": "user", "content": "你好"}])

        assert result["saved"] is False
        assert result["skip_reason"] == "no_user_id"
        assert result["portrait_text"] == ""
        assert result["knowledge_text"] == ""
        assert result["attempts_used"] == 0

    @pytest.mark.asyncio
    async def test_skip_when_no_messages(self):
        """messages 为空时 saved=False，skip_reason=no_messages。"""
        uid = "00000000-0000-0000-0008-000000000101"
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        manager = MemoryManager(user_id=uid, memory_db=db)
        result = await manager.form_memory([])

        assert result["saved"] is False
        assert result["skip_reason"] == "no_messages"
        assert result["portrait_text"] == ""
        assert result["knowledge_text"] == ""
        assert result["attempts_used"] == 0

    @pytest.mark.asyncio
    async def test_skip_does_not_call_llm_or_save(self):
        """跳过场景不应调用 LLM 或落库。"""
        uid = "00000000-0000-0000-0008-000000000102"
        queue = MagicMock()
        queue.submit = AsyncMock()
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        # 无 messages 场景
        manager = MemoryManager(user_id=uid, api_queue=queue, memory_db=db)
        await manager.form_memory([])

        queue.submit.assert_not_awaited()
        db.save_profile.assert_not_awaited()

        # 无 user_id 场景
        manager2 = MemoryManager(api_queue=queue, memory_db=db)
        await manager2.form_memory([{"role": "user", "content": "你好"}])

        queue.submit.assert_not_awaited()
        db.save_profile.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_save_profile_receives_new_key_names(self):
        """save_profile 应接收 portrait_text 和 knowledge_text。"""
        uid = "00000000-0000-0000-0008-000000000103"
        queue = MagicMock()
        queue.submit = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"confirmed":{"identity":[],"interests":[],"constraints":[]},"hypothesized":{"identity":[],"interests":[]},"knowledge":{"confirmed_facts":["已确认"],"pending_queries":[]}}'
                        )
                    )
                ]
            )
        )
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory([{"role": "user", "content": "你好"}])

        # 验证 save_profile 被调用，参数为 uid, portrait_text, knowledge_text
        db.save_profile.assert_awaited_once_with(
            uid,
            result["portrait_text"],
            result["knowledge_text"],
        )
        assert "已确认" in result["knowledge_text"]


class TestMemoryManager:
    """MemoryManager 测试套件。"""

    @pytest.mark.asyncio
    async def test_form_memory_returns_skip_when_no_user(self):
        """未提供用户时应跳过记忆形成（v2 契约）。"""
        manager = MemoryManager()

        result = await manager.form_memory([{"role": "user", "content": "你好"}])

        assert result["saved"] is False
        assert result["skip_reason"] == "no_user_id"
        assert result["portrait_text"] == ""
        assert result["knowledge_text"] == ""

    @pytest.mark.asyncio
    async def test_form_memory_calls_queue_and_save_profile(self):
        """应调用 LLM 队列并保存画像（v2 契约）。"""
        uid_a = "00000000-0000-0000-0008-000000000001"

        queue = MagicMock()
        queue.submit = AsyncMock(
            return_value=MagicMock(
                choices=[
                    MagicMock(
                        message=MagicMock(
                            content='{"confirmed":{"identity":["北京"],"interests":["内科"],"constraints":[]},"hypothesized":{"identity":[],"interests":[]},"knowledge":{"confirmed_facts":["已确认"],"pending_queries":["待查"]}}'
                        )
                    )
                ]
            )
        )

        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(
                user_id=uid_a,
                conversation_id="conv-1",
                memory_db=db,
            )
            result = await manager.form_memory([{"role": "user", "content": "我想去北京读内科"}])

        queue.submit.assert_awaited_once()
        db.save_profile.assert_awaited_once_with(
            uid_a,
            result["portrait_text"],
            result["knowledge_text"],
        )
        assert "北京" in result["portrait_text"]
        assert "已确认" in result["knowledge_text"]

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


class TestV2SchemaValidationAndIdentityAdjudication:
    """v2 校验与 identity 裁决测试（TDD Task 3 RED）。"""

    # ---- _parse_memory 直接测试（无需 mock） ----

    def test_v2_valid_json_produces_portrait_and_knowledge(self):
        """v2 合法 JSON 应通过解析并生成 portrait_text / knowledge_text。"""
        manager = MemoryManager()
        v2_json = json.dumps({
            "confirmed": {
                "identity": ["大三学生", "计算机专业"],
                "interests": ["编程", "AI"],
                "constraints": ["广州"],
            },
            "hypothesized": {
                "identity": ["可能对研究生感兴趣"],
                "interests": ["深度学习"],
            },
            "knowledge": {
                "confirmed_facts": ["用户已确认是大三学生"],
                "pending_queries": ["是否准备考研"],
            },
        }, ensure_ascii=False)

        result = manager._parse_memory(v2_json)

        assert result["portrait_text"] != "", "portrait_text 不应为空"
        assert result["knowledge_text"] != "", "knowledge_text 不应为空"

        portrait = json.loads(result["portrait_text"])
        knowledge = json.loads(result["knowledge_text"])

        # 确认画像包含 confirmed 和 hypothesized
        assert "confirmed" in portrait
        assert "hypothesized" in portrait
        assert "大三学生" in portrait["confirmed"]["identity"]

        # 确认知识包含 confirmed_facts
        assert "confirmed_facts" in knowledge
        assert "用户已确认是大三学生" in knowledge["confirmed_facts"]

    def test_v1_json_treated_as_empty_portrait(self):
        """v1 格式（hard_constraints 等字段）应被视为空画像。"""
        manager = MemoryManager()
        v1_json = json.dumps({
            "hard_constraints": ["广州"],
            "soft_constraints": ["编程"],
            "risk_tolerance": "low",
            "verified_facts": ["用户是学生"],
        }, ensure_ascii=False)

        result = manager._parse_memory(v1_json)

        assert result["portrait_text"] == "", "v1 JSON 的 portrait_text 应为空"
        assert result["knowledge_text"] == "", "v1 JSON 的 knowledge_text 应为空"

    def test_identity_inferred_items_demoted_to_hypothesized(self):
        """confirmed.identity 中含推断关键词的条目应降级到 hypothesized.identity。"""
        manager = MemoryManager()
        v2_json = json.dumps({
            "confirmed": {
                "identity": ["大三学生", "可能对考研感兴趣"],
                "interests": ["编程"],
                "constraints": [],
            },
            "hypothesized": {
                "identity": ["推测喜欢AI"],
                "interests": [],
            },
            "knowledge": {
                "confirmed_facts": [],
                "pending_queries": [],
            },
        }, ensure_ascii=False)

        result = manager._parse_memory(v2_json)
        portrait = json.loads(result["portrait_text"])

        # "可能对考研感兴趣" 含"可能"，应被降级（可能带（来源未确认）前缀）
        assert "可能对考研感兴趣" not in portrait["confirmed"]["identity"], \
            "含推断关键词的条目不应留在 confirmed.identity"
        hypo_identity = portrait["hypothesized"]["identity"]
        assert any("可能对考研感兴趣" in item for item in hypo_identity), \
            "含推断关键词的条目应降级到 hypothesized.identity"

        # "推测喜欢AI" 已在 hypothesized 中，不受影响
        assert "推测喜欢AI" in portrait["hypothesized"]["identity"]

        # "大三学生" 不含推断词，应留在 confirmed
        assert "大三学生" in portrait["confirmed"]["identity"]

    def test_demoted_item_lacks_source_gets_prefix(self):
        """降级条目缺少来源标注时，自动补上（来源未确认）前缀。"""
        manager = MemoryManager()
        v2_json = json.dumps({
            "confirmed": {
                "identity": ["频繁阅读计算机文章"],
                "interests": [],
                "constraints": [],
            },
            "hypothesized": {
                "identity": [],
                "interests": [],
            },
            "knowledge": {
                "confirmed_facts": [],
                "pending_queries": [],
            },
        }, ensure_ascii=False)

        result = manager._parse_memory(v2_json)
        portrait = json.loads(result["portrait_text"])

        # "频繁阅读计算机文章" 含"频繁阅读"，应被降级
        hypo_identity = portrait["hypothesized"]["identity"]
        # 应该在 hypothesized 中找到带来源前缀的版本
        matched = [item for item in hypo_identity if "频繁阅读计算机文章" in item]
        assert len(matched) > 0, "降级条目应出现在 hypothesized.identity 中"
        assert any("（来源未确认）" in item for item in matched), \
            "缺来源标注的降级条目应自动补上（来源未确认）"

    def test_demoted_item_with_source_keeps_original(self):
        """降级条目已有来源标注时，不重复添加（来源未确认）。"""
        manager = MemoryManager()
        v2_json = json.dumps({
            "confirmed": {
                "identity": ["可能对AI感兴趣（来源：多次查询AI话题）"],
                "interests": [],
                "constraints": [],
            },
            "hypothesized": {
                "identity": [],
                "interests": [],
            },
            "knowledge": {
                "confirmed_facts": [],
                "pending_queries": [],
            },
        }, ensure_ascii=False)

        result = manager._parse_memory(v2_json)
        portrait = json.loads(result["portrait_text"])

        hypo_identity = portrait["hypothesized"]["identity"]
        matched = [item for item in hypo_identity if "可能对AI感兴趣" in item]
        assert len(matched) > 0
        # 已有来源标注，不应再添加（来源未确认）
        assert not any("（来源未确认）" in item and "（来源：" in item for item in matched), \
            "已有来源标注的条目不应重复添加（来源未确认）"

    def test_invalid_json_returns_empty(self):
        """非法 JSON 字符串应返回空画像和空知识。"""
        manager = MemoryManager()

        result = manager._parse_memory("this is not json{{{")

        assert result["portrait_text"] == ""
        assert result["knowledge_text"] == ""

    def test_normalize_string_list_with_single_string(self):
        """_normalize_string_list 接受单字符串应返回包含该字符串的列表。"""
        result = MemoryManager._normalize_string_list("hello")
        assert result == ["hello"]

    def test_normalize_string_list_with_list(self):
        """_normalize_string_list 接受列表应原样返回（过滤空串）。"""
        result = MemoryManager._normalize_string_list(["a", "", "b"])
        assert result == ["a", "b"]

    def test_normalize_string_list_with_non_string(self):
        """_normalize_string_list 应过滤非字符串元素。"""
        result = MemoryManager._normalize_string_list(["a", 123, None, "b"])
        assert result == ["a", "b"]

    def test_v2_partial_structure_still_works(self):
        """v2 JSON 只包含部分字段时，缺失字段用空列表填充。"""
        manager = MemoryManager()
        v2_json = json.dumps({
            "confirmed": {
                "identity": ["学生"],
            },
            "knowledge": {},
        }, ensure_ascii=False)

        result = manager._parse_memory(v2_json)

        assert result["portrait_text"] != ""
        portrait = json.loads(result["portrait_text"])
        assert portrait["confirmed"]["identity"] == ["学生"]
        assert portrait["confirmed"]["interests"] == []
        assert portrait["hypothesized"]["identity"] == []

    def test_v2_mixed_v1_keys_treated_as_empty(self):
        """JSON 同时含 v1 和 v2 字段但不含 confirmed，视为空画像。"""
        manager = MemoryManager()
        mixed_json = json.dumps({
            "hard_constraints": ["广州"],
            "soft_constraints": ["编程"],
        }, ensure_ascii=False)

        result = manager._parse_memory(mixed_json)

        assert result["portrait_text"] == ""
        assert result["knowledge_text"] == ""


class TestRetryProtocol:
    """重试协议测试（TDD Task 4 RED）。

    可重试错误（内容错误）：非 JSON、v2 校验失败、字段类型错误。
    不可重试错误（基础设施错误）：DB 写入异常。
    最多 3 次尝试，失败超限返回 saved=false。
    """

    @staticmethod
    def _make_response(content: str) -> MagicMock:
        """构造 LLM 返回的 mock response 对象。"""
        return MagicMock(
            choices=[MagicMock(message=MagicMock(content=content))]
        )

    @staticmethod
    def _valid_v2_response() -> MagicMock:
        """构造合法 v2 JSON 的 mock response。"""
        return TestRetryProtocol._make_response(
            '{"confirmed":{"identity":["大三"],"interests":["编程"],"constraints":[]},'
            '"hypothesized":{"identity":[],"interests":[]},'
            '"knowledge":{"confirmed_facts":["已确认"],"pending_queries":[]}}'
        )

    @staticmethod
    def _invalid_response() -> MagicMock:
        """构造非 JSON（解析失败）的 mock response。"""
        return TestRetryProtocol._make_response("this is not json at all!!!")

    @pytest.mark.asyncio
    async def test_first_fail_second_success_attempts_used_2(self):
        """非 JSON 第 1 次失败，第 2 次成功，attempts_used=2，saved=True。"""
        uid = "00000000-0000-0000-0008-000000000200"
        queue = MagicMock()
        # 第 1 次返回非法内容，第 2 次返回合法 v2 JSON
        queue.submit = AsyncMock(
            side_effect=[
                self._invalid_response(),
                self._valid_v2_response(),
            ]
        )
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory([{"role": "user", "content": "你好"}])

        assert result["saved"] is True, "第 2 次成功应 saved=True"
        assert result["attempts_used"] == 2, f"应 attempts_used=2，实际={result['attempts_used']}"
        assert result["last_error"] == "", "最终成功后 last_error 应为空"
        assert result["skip_reason"] == "", "最终成功后 skip_reason 应为空"
        # save_profile 只应被调用一次（成功那次）
        db.save_profile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_three_consecutive_failures_saved_false(self):
        """连续 3 次失败，saved=False，attempts_used=3，skip_reason=max_retries_exceeded。"""
        uid = "00000000-0000-0000-0008-000000000201"
        queue = MagicMock()
        # 3 次都返回非法内容
        queue.submit = AsyncMock(
            side_effect=[
                self._invalid_response(),
                self._invalid_response(),
                self._invalid_response(),
            ]
        )
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory([{"role": "user", "content": "你好"}])

        assert result["saved"] is False, "3 次失败应 saved=False"
        assert result["attempts_used"] == 3, f"应 attempts_used=3，实际={result['attempts_used']}"
        assert result["skip_reason"] == "max_retries_exceeded"
        assert result["last_error"] != "", "失败后 last_error 不应为空"
        assert result["portrait_text"] == ""
        assert result["knowledge_text"] == ""
        # 3 次都失败，不应调用 save_profile
        db.save_profile.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retry_prompt_contains_messages_and_last_error_only(self):
        """重试请求仅包含 messages + last_error，不追加已保存画像。"""
        uid = "00000000-0000-0000-0008-000000000202"
        queue = MagicMock()
        captured_prompts: list[str] = []

        async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
            captured_prompts.append(prompt)
            # 第 1 次失败，第 2 次成功
            if len(captured_prompts) == 1:
                return self._invalid_response()
            return self._valid_v2_response()

        queue.submit = AsyncMock(side_effect=capture_submit)
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        messages = [{"role": "user", "content": "你好"}]

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory(messages)

        assert result["saved"] is True
        assert len(captured_prompts) == 2, "应捕获 2 次 prompt"

        # 第 2 次 prompt 应包含错误信息（重试特征）
        retry_prompt = captured_prompts[1]
        assert "你好" in retry_prompt, "重试 prompt 应包含原始对话内容"
        assert "第1次尝试" in retry_prompt, "重试 prompt 应包含上次错误信息"
        assert "请严格按要求输出合法 JSON" in retry_prompt, "重试 prompt 应包含修正指令"

    @pytest.mark.asyncio
    async def test_retry_prompt_does_not_include_existing_profile_section(self):
        """重试 prompt 不应注入已有用户画像段落。"""
        uid = "00000000-0000-0000-0008-000000000204"
        queue = MagicMock()
        captured_prompts: list[str] = []

        async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
            captured_prompts.append(prompt)
            if len(captured_prompts) == 1:
                return self._invalid_response()
            return self._valid_v2_response()

        queue.submit = AsyncMock(side_effect=capture_submit)
        db = MagicMock()
        db.save_profile = AsyncMock()
        # 模拟 DB 中有有效 v2 画像
        db.get_profile = AsyncMock(return_value={
            "portrait_text": '{"confirmed":{"identity":["大三学生"],"interests":["编程"],"constraints":[]},"hypothesized":{"identity":[],"interests":[]}}',
            "knowledge_text": '{"confirmed_facts":["六级550分"],"pending_queries":["分数线"]}',
        })

        messages = [{"role": "user", "content": "你好"}]

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            result = await manager.form_memory(messages)

        assert result["saved"] is True
        assert len(captured_prompts) == 2, "应捕获 2 次 prompt"

        retry_prompt = captured_prompts[1]
        assert "已有用户画像（仅供参考" not in retry_prompt, \
            "重试 prompt 不应包含已有用户画像段落"

    @pytest.mark.asyncio
    async def test_db_exception_is_not_retried_and_propagates(self):
        """DB 异常属于不可重试错误，直接抛出，不进行重试。"""
        uid = "00000000-0000-0000-0008-000000000203"
        queue = MagicMock()
        queue.submit = AsyncMock(return_value=self._valid_v2_response())
        db = MagicMock()
        # 模拟 DB 写入异常
        db.save_profile = AsyncMock(side_effect=RuntimeError("数据库连接断开"))
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            with pytest.raises(RuntimeError, match="数据库连接断开"):
                await manager.form_memory([{"role": "user", "content": "你好"}])

        # LLM 只调用了一次（DB 错误不应触发重试）
        queue.submit.assert_awaited_once()


class TestExistingProfileInjection:
    """已有画像注入首轮 prompt 测试（TDD RED → GREEN）。"""

    @staticmethod
    def _make_response(content: str) -> MagicMock:
        return MagicMock(
            choices=[MagicMock(message=MagicMock(content=content))]
        )

    @staticmethod
    def _valid_v2_response() -> MagicMock:
        return TestExistingProfileInjection._make_response(
            '{"confirmed":{"identity":["大三"],"interests":["编程"],"constraints":[]},'
            '"hypothesized":{"identity":[],"interests":[]},'
            '"knowledge":{"confirmed_facts":["已确认"],"pending_queries":[]}}'
        )

    @pytest.mark.asyncio
    async def test_first_prompt_skips_existing_profile_when_v1(self):
        """v1 格式画像时，首轮 prompt 不应包含已有画像段落。"""
        uid = "00000000-0000-0000-0008-000000000301"
        queue = MagicMock()
        captured_prompts: list[str] = []

        async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
            captured_prompts.append(prompt)
            return self._valid_v2_response()

        queue.submit = AsyncMock(side_effect=capture_submit)
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value={
            "portrait_text": '{"hard_constraints":["广州"],"soft_constraints":["编程"],"risk_tolerance":"low","verified_facts":["用户是学生"]}',
            "knowledge_text": '{}',
        })

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            await manager.form_memory([{"role": "user", "content": "你好"}])

        first_prompt = captured_prompts[0]
        assert "已有用户画像（仅供参考" not in first_prompt, \
            "v1 画像时首轮 prompt 不应包含已有画像段落"

    @pytest.mark.asyncio
    async def test_first_prompt_skips_existing_profile_when_invalid_json(self):
        """非法 JSON 画像时，首轮 prompt 不应包含已有画像段落。"""
        uid = "00000000-0000-0000-0008-000000000302"
        queue = MagicMock()
        captured_prompts: list[str] = []

        async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
            captured_prompts.append(prompt)
            return self._valid_v2_response()

        queue.submit = AsyncMock(side_effect=capture_submit)
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value={
            "portrait_text": "this is not valid json{{{",
            "knowledge_text": "",
        })

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            await manager.form_memory([{"role": "user", "content": "你好"}])

        first_prompt = captured_prompts[0]
        assert "已有用户画像（仅供参考" not in first_prompt, \
            "非法 JSON 画像时首轮 prompt 不应包含已有画像段落"

    @pytest.mark.asyncio
    async def test_first_prompt_skips_existing_profile_when_no_profile(self):
        """无画像时，首轮 prompt 不应包含已有画像段落。"""
        uid = "00000000-0000-0000-0008-000000000303"
        queue = MagicMock()
        captured_prompts: list[str] = []

        async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
            captured_prompts.append(prompt)
            return self._valid_v2_response()

        queue.submit = AsyncMock(side_effect=capture_submit)
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value=None)

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            await manager.form_memory([{"role": "user", "content": "你好"}])

        first_prompt = captured_prompts[0]
        assert "已有用户画像（仅供参考" not in first_prompt, \
            "无画像时首轮 prompt 不应包含已有画像段落"

    @pytest.mark.asyncio
    async def test_first_prompt_adjudicates_inferred_identity_from_existing_profile(self):
        """已有画像注入时，也应对 confirmed.identity 做推断裁决。"""
        uid = "00000000-0000-0000-0008-000000000304"
        queue = MagicMock()
        captured_prompts: list[str] = []

        async def capture_submit(lane: str, fn_or_sync: object, prompt: str) -> MagicMock:
            captured_prompts.append(prompt)
            return self._valid_v2_response()

        queue.submit = AsyncMock(side_effect=capture_submit)
        db = MagicMock()
        db.save_profile = AsyncMock()
        db.get_profile = AsyncMock(return_value={
            "portrait_text": '{"confirmed":{"identity":["可能是大三学生"],"interests":[],"constraints":[]},"hypothesized":{"identity":[],"interests":[]}}',
            "knowledge_text": '{}',
        })

        with patch("src.chat.memory_manager.get_api_queue", return_value=queue):
            manager = MemoryManager(user_id=uid, memory_db=db)
            await manager.form_memory([{"role": "user", "content": "你好"}])

        first_prompt = captured_prompts[0]
        assert "已确认身份: 可能是大三学生" not in first_prompt, \
            "推断型 identity 不应以已确认身份注入 prompt"
        assert "推测身份: （来源未确认）可能是大三学生" in first_prompt, \
            "推断型 identity 应降级并带来源前缀后注入 prompt"