"""旧 AI End 兼容请求模型"""

from uuid import UUID

from pydantic import BaseModel, field_validator


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
