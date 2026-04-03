"""
聊天模块 - OpenAI 客户端集成与技能系统
"""

__all__ = ["ChatClient"]


def __getattr__(name: str):
    if name == "ChatClient":
        from src.chat.client import ChatClient

        return ChatClient
    raise AttributeError(name)
