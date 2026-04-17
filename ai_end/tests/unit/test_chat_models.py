"""ChatRequest 模型测试 — 用户资料字段扩展"""
import pytest
from pydantic import ValidationError

from src.api.models import ChatRequest

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


class TestChatRequest:
    def test_basic_fields_required(self):
        """message 和 user_id 必填"""
        with pytest.raises(ValidationError):
            ChatRequest()

    def test_basic_fields_valid(self):
        req = ChatRequest(message="hello", user_id=VALID_UUID)
        assert req.message == "hello"
        assert req.user_id == VALID_UUID
        assert req.conversation_id is None
        assert req.display_name is None
        assert req.profile_tags is None
        assert req.bio is None

    def test_profile_fields_optional(self):
        req = ChatRequest(
            message="hi",
            user_id=VALID_UUID,
            display_name="张三",
            profile_tags=["计算机", "夜猫子"],
            bio="大三学生",
            conversation_id="conv-1",
        )
        assert req.display_name == "张三"
        assert req.profile_tags == ["计算机", "夜猫子"]
        assert req.bio == "大三学生"
        assert req.conversation_id == "conv-1"

    def test_profile_tags_empty_list_ok(self):
        req = ChatRequest(
            message="hi",
            user_id=VALID_UUID,
            profile_tags=[],
        )
        assert req.profile_tags == []

    def test_invalid_uuid_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", user_id="not-a-uuid")
