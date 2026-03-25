"""OpenAI API 客户端单例管理。"""

from collections.abc import Callable

from openai import OpenAI

from src.config.settings import Config

_llm_client: OpenAI | None = None
_embedding_client: OpenAI | None = None
_rerank_client: OpenAI | None = None


def get_llm_client(factory: Callable[[], OpenAI] | None = None) -> OpenAI:
    """获取 LLM 客户端单例。"""
    global _llm_client
    if _llm_client is None:
        if factory is not None:
            _llm_client = factory()
        else:
            config = Config.load()
            _llm_client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.llm_timeout,
            )
    return _llm_client


def get_embedding_client(factory: Callable[[], OpenAI] | None = None) -> OpenAI:
    """获取 Embedding 客户端单例。"""
    global _embedding_client
    if _embedding_client is None:
        if factory is not None:
            _embedding_client = factory()
        else:
            config = Config.load()
            api_key = config.embedding_api_key or config.api_key
            base_url = config.embedding_base_url or config.base_url
            _embedding_client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=config.embedding_timeout,
            )
    return _embedding_client


def get_rerank_client(factory: Callable[[], OpenAI] | None = None) -> OpenAI:
    """获取 Rerank 客户端单例。"""
    global _rerank_client
    if _rerank_client is None:
        if factory is not None:
            _rerank_client = factory()
        else:
            config = Config.load()
            api_key = config.rerank_api_key or config.api_key
            base_url = config.effective_rerank_base_url
            _rerank_client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=config.rerank_timeout,
            )
    return _rerank_client


def close_clients() -> None:
    """关闭已创建的客户端，幂等。"""
    global _llm_client, _embedding_client, _rerank_client

    clients_to_close = [
        (_llm_client, "_llm_client"),
        (_embedding_client, "_embedding_client"),
        (_rerank_client, "_rerank_client"),
    ]

    for client, name in clients_to_close:
        try:
            if client is not None and hasattr(client, "close"):
                client.close()
        except Exception as e:
            # 记录但继续关闭其他客户端
            import logging
            logging.getLogger(__name__).warning(
                "Error closing %s: %s", name, e
            )

    _llm_client = None
    _embedding_client = None
    _rerank_client = None
