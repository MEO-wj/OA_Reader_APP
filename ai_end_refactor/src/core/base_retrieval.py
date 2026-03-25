"""检索系统基类，提供文本语义检索的共享逻辑。"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from src.config.settings import Config
from src.core.api_clients import get_embedding_client
from src.core.api_queue import get_api_queue
from src.core.db import get_pool


class BaseRetriever(ABC):
    """文本语义检索基类。"""

    def __init__(
        self,
        table_name: str,
        select_columns: list[str],
        embedding_column: str = "embedding",
        *,
        get_pool_fn: Callable[[], Awaitable[Any]] | None = None,
        rerank_fn: Callable[[str, list[dict[str, Any]], int | None], Awaitable[list[dict[str, Any]]]] | None = None,
        is_transient_error: Callable[[Exception], bool] | None = None,
        retry_attempts: int = 3,
        retry_backoff: float = 0.05,
    ):
        self.table_name = table_name
        self.select_columns = select_columns
        self.embedding_column = embedding_column
        self._get_pool_fn = get_pool_fn or get_pool
        self._rerank_fn = rerank_fn
        self._is_transient_error = is_transient_error
        self._retry_attempts = retry_attempts
        self._retry_backoff = retry_backoff

    @abstractmethod
    async def _build_metadata_filter(
        self,
        start_index: int = 1,
        **filters: Any,
    ) -> tuple[str, list[Any]]:
        """子类实现：构建元数据过滤条件。"""

    async def _vector_search(
        self,
        query_embedding_str: str,
        limit: int = 20,
        threshold: float = 0.5,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Layer 1: 向量搜索。"""
        selected = ", ".join(self.select_columns)
        where_clauses = [
            f"{self.embedding_column} IS NOT NULL",
            f"1 - ({self.embedding_column} <=> $1::vector) >= $2",
        ]
        params: list[Any] = [query_embedding_str, threshold]

        if metadata_filters:
            filter_clause, filter_params = await self._build_metadata_filter(
                start_index=3,
                **metadata_filters,
            )
            if filter_clause:
                where_clauses.append(f"({filter_clause})")
                params.extend(filter_params)

        params.append(limit)
        limit_idx = len(params)
        sql = f"""
            SELECT {selected},
                   1 - ({self.embedding_column} <=> $1::vector) as similarity
            FROM {self.table_name}
            WHERE {' AND '.join(where_clauses)}
            ORDER BY {self.embedding_column} <=> $1::vector
            LIMIT ${limit_idx}
        """

        last_error: Exception | None = None
        for attempt in range(self._retry_attempts):
            try:
                pool = await self._get_pool_fn()
                async with pool.acquire() as conn:
                    rows = await conn.fetch(sql, *params)
                return list(rows)
            except Exception as exc:
                last_error = exc
                transient = self._is_transient_error(exc) if self._is_transient_error else False
                if transient and attempt < self._retry_attempts - 1:
                    await asyncio.sleep(self._retry_backoff)
                    continue
                break

        if last_error is not None and self._is_transient_error and self._is_transient_error(last_error):
            raise RuntimeError("TRANSIENT_DB_ERROR") from last_error
        if last_error is not None:
            raise last_error
        return []

    async def _rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Layer 3: 重排序。"""
        if not candidates:
            return []

        if self._rerank_fn is None:
            return candidates[:top_k]

        try:
            return await self._rerank_fn(query, candidates, top_k)
        except Exception:
            return candidates[:top_k]


def _generate_embedding_sync(text: str) -> list[float]:
    """同步生成文本向量。"""
    if not text or not text.strip():
        raise ValueError("文本不能为空")

    config = Config.load()
    client = get_embedding_client()
    response = client.embeddings.create(
        model=config.embedding_model,
        input=text,
        dimensions=config.embedding_dimensions,
    )
    return response.data[0].embedding


async def generate_embedding(text: str) -> list[float]:
    """异步生成文本向量。"""
    return await get_api_queue().submit("embedding", _generate_embedding_sync, text)
