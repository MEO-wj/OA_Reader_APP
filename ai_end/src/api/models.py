"""API 请求/响应模型"""

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """聊天请求"""

    message: str
    user_id: str = Field(min_length=1, max_length=64)  # 限制长度，避免数据库约束错误
    conversation_id: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    profile_tags: list[str] | None = None
    bio: str | None = None

    @field_validator("top_k", mode="before")
    @classmethod
    def _reject_bool_top_k(cls, v: object) -> object:
        if isinstance(v, bool):
            raise ValueError("top_k must be an integer or string, not boolean")
        return v

    @field_validator("user_id")
    @classmethod
    def _validate_user_id_uuid(cls, v: str) -> str:
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc


class ConversationCreate(BaseModel):
    """创建会话请求"""

    user_id: str = Field(min_length=1, max_length=64)
    title: str | None = None

    @field_validator("user_id")
    @classmethod
    def _validate_user_id_uuid(cls, v: str) -> str:
        try:
            return str(UUID(v))
        except ValueError as exc:
            raise ValueError("user_id must be a valid UUID") from exc


class ConversationResponse(BaseModel):
    """会话响应"""

    user_id: str
    conversation_id: str
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationListResponse(BaseModel):
    """会话列表响应"""

    user_id: str
    sessions: list[ConversationResponse]
    count: int


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    version: str


class SkillInfo(BaseModel):
    """技能信息"""

    name: str
    description: str


class SkillsResponse(BaseModel):
    """技能列表响应"""

    skills: list[SkillInfo]
    data_source: str = "database"  # 数据源：database 或 filesystem
    skill_count: int = 0  # 技能数量
