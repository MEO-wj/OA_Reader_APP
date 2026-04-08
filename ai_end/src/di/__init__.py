"""依赖注入模块。"""

from src.di.container import AppContainer
from src.di.providers import (
    get_container,
    get_chat_service,
    get_history_manager,
    get_memory_manager,
    get_chat_client,
    get_skill_system,
    create_chat_client,
)

__all__ = [
    "AppContainer",
    "create_chat_client",
    "get_container",
    "get_chat_client",
    "get_chat_service",
    "get_history_manager",
    "get_memory_manager",
    "get_skill_system",
]
