"""便捷 provider 访问入口。"""

from __future__ import annotations

from src.di.container import AppContainer
from src.core.skill_adapter import SkillBackend

_container: AppContainer | None = None


def get_container() -> AppContainer:
    """获取全局容器实例。"""
    global _container
    if _container is None:
        _container = AppContainer()
    return _container


def get_skill_system(
    *,
    backend: SkillBackend = SkillBackend.FILESYSTEM,
    skills_dir: str = "./skills",
):
    """获取技能系统实例。"""
    container = get_container()
    if backend == SkillBackend.FILESYSTEM:
        if skills_dir == "./skills":
            return container.skill_system()
        return container.skill_system_factory(
            backend=backend,
            skills_dir=skills_dir,
        )
    if backend == SkillBackend.DATABASE:
        return container.skill_system_factory(
            backend=backend,
            skills_dir=skills_dir,
        )
    raise ValueError(f"Unsupported skill backend: {backend}")


def get_memory_manager(
    user_id: str | None = None,
    conversation_id: str | None = None,
    **kwargs,
):
    """获取记忆管理器实例。"""
    return get_container().memory_manager_factory(
        user_id=user_id,
        conversation_id=conversation_id,
        **kwargs,
    )


def get_history_manager(
    user_id: str | None = None,
    conversation_id: str | None = None,
    **kwargs,
):
    """获取历史管理器实例。"""
    return get_container().history_manager_factory(
        user_id=user_id,
        conversation_id=conversation_id,
        **kwargs,
    )


def get_chat_client(config):
    """获取同步聊天客户端。"""
    from src.chat.client import ChatClient

    return ChatClient(config)


async def create_chat_client(
    config,
    user_id: str | None = None,
    conversation_id: str | None = None,
    user_profile: dict | None = None,
):
    """获取异步聊天客户端。"""
    from src.chat.client import ChatClient

    return await ChatClient.create(config, user_id, conversation_id, user_profile=user_profile)


def get_chat_service(
    user_id: str | None = None,
    conversation_id: str | None = None,
    user_profile: dict | None = None,
):
    """获取聊天服务实例。"""
    from src.api.chat_service import ChatService

    return ChatService(user_id=user_id, conversation_id=conversation_id, user_profile=user_profile)
