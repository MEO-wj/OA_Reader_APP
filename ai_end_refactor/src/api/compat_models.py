"""旧 AI End 兼容请求模型"""

from pydantic import BaseModel, field_validator


class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None

    @field_validator("top_k", mode="before")
    @classmethod
    def _reject_bool_top_k(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError("top_k must be an integer or string, not boolean")
        return v


class ClearMemoryCompatRequest(BaseModel):
    user_id: str | None = None


class EmbedCompatRequest(BaseModel):
    text: str | None = None
