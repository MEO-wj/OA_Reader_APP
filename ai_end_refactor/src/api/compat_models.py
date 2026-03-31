"""旧 AI End 兼容请求模型"""

from pydantic import BaseModel


class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None


class ClearMemoryCompatRequest(BaseModel):
    user_id: str | None = None


class EmbedCompatRequest(BaseModel):
    text: str | None = None
