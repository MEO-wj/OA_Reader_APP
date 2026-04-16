import pytest
from pydantic import ValidationError

from src.api.models import (
    ChatRequest,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
)
from src.api.compat_models import ClearMemoryCompatRequest

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"


def test_chat_request_accepts_optional_conversation_id():
    req = ChatRequest(message="hi", user_id=VALID_UUID, conversation_id="conv1")
    assert req.conversation_id == "conv1"


def test_conversation_models_basic_fields():
    create = ConversationCreate(user_id=VALID_UUID, title="考研咨询")
    assert create.user_id == VALID_UUID
    assert create.title == "考研咨询"

    session = ConversationResponse(
        user_id=VALID_UUID,
        conversation_id="conv1",
        title="会话1",
    )
    resp = ConversationListResponse(user_id=VALID_UUID, sessions=[session], count=1)

    assert resp.count == 1
    assert resp.sessions[0].conversation_id == "conv1"


# ---------------------------------------------------------------------------
# UUID 校验测试
# ---------------------------------------------------------------------------


def test_chat_request_rejects_invalid_user_id_uuid():
    with pytest.raises(ValidationError, match="user_id must be a valid UUID"):
        ChatRequest(message="hi", user_id="u1")


def test_conversation_create_accepts_uuid_user_id():
    req = ConversationCreate(user_id=VALID_UUID, title="考研咨询")
    assert req.user_id == VALID_UUID


def test_compat_models_validate_uuid_user_id():
    with pytest.raises(ValidationError, match="user_id must be a valid UUID"):
        ClearMemoryCompatRequest(user_id="bad-user")

    # valid UUID should pass
    req = ClearMemoryCompatRequest(user_id=VALID_UUID)
    assert req.user_id == VALID_UUID
