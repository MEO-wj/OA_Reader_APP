"""BaseRetriever 单元测试。"""

import pytest

from src.core.base_retrieval import BaseRetriever


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class DummyRetriever(BaseRetriever):
    async def _build_metadata_filter(self, start_index: int = 1, **filters):
        if not filters:
            return "", []
        return f"category = ${start_index}", [filters["category"]]


@pytest.mark.asyncio
async def test_vector_search_success_with_metadata_filter():
    calls = {"sql": None, "args": None}

    class Conn:
        async def fetch(self, sql, *args):
            calls["sql"] = sql
            calls["args"] = args
            return [{"id": 1, "title": "A", "summary": "B", "created_at": None, "similarity": 0.8}]

    async def fake_get_pool():
        return _Pool(Conn())

    retriever = DummyRetriever(
        table_name="policies",
        select_columns=["id", "title", "summary", "created_at"],
        get_pool_fn=fake_get_pool,
    )

    results = await retriever._vector_search(
        query_embedding_str="[0.1,0.2]",
        limit=5,
        threshold=0.6,
        metadata_filters={"category": "x"},
    )

    assert len(results) == 1
    assert "category = $3" in calls["sql"]
    assert calls["args"] == ("[0.1,0.2]", 0.6, "x", 5)


@pytest.mark.asyncio
async def test_vector_search_transient_error_returns_marker_runtime_error():
    class Conn:
        async def fetch(self, *args, **kwargs):
            raise Exception("connection was closed")

    async def fake_get_pool():
        return _Pool(Conn())

    retriever = DummyRetriever(
        table_name="policies",
        select_columns=["id"],
        get_pool_fn=fake_get_pool,
        is_transient_error=lambda e: "connection was closed" in str(e),
    )

    with pytest.raises(RuntimeError, match="TRANSIENT_DB_ERROR"):
        await retriever._vector_search("[0.1,0.2]")
