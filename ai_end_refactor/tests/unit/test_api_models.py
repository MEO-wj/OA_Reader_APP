from src.api.models import (
    ChatRequest,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
)


def test_chat_request_accepts_optional_conversation_id():
    req = ChatRequest(message="hi", user_id="u1", conversation_id="conv1")
    assert req.conversation_id == "conv1"


def test_conversation_models_basic_fields():
    create = ConversationCreate(user_id="u1", title="考研咨询")
    assert create.user_id == "u1"
    assert create.title == "考研咨询"

    session = ConversationResponse(
        user_id="u1",
        conversation_id="conv1",
        title="会话1",
    )
    resp = ConversationListResponse(user_id="u1", sessions=[session], count=1)

    assert resp.count == 1
    assert resp.sessions[0].conversation_id == "conv1"
