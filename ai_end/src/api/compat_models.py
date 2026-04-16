"""旧 AI End 兼容请求模型"""

from uuid import UUID

from pydantic import BaseModel, field_validator


class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None
    conversation_id: str | None = None

    @field_validator("top_k", mode="before")
    @classmethod
    def _reject_bool_top_k(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError("top_k must be an integer or string, not boolean")
        return v

    @field_validator("user_id")
    @classmethod
    def _validate_user_id_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc


class ClearMemoryCompatRequest(BaseModel):
    user_id: str | None = None

    @field_validator("user_id")
    @classmethod
    def _validate_user_id_uuid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc


class EmbedCompatRequest(BaseModel):
    text: str | None = None
