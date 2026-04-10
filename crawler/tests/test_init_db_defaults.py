"""init_db 默认值修复测试

验证 init_db 执行后，articles 和 vectors 表的 created_at / updated_at 列
具备 DEFAULT NOW()，确保非 GORM 写入路径也能自动填充时间戳。

运行方式：
    DATABASE_URL="postgresql://..." uv run pytest tests/test_init_db_defaults.py -v
"""

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timedelta

import pytest


def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key == "DATABASE_URL" and not os.environ.get(key):
                    os.environ[key] = value.strip()


_load_env()

DATABASE_URL = os.environ.get("DATABASE_URL")
SKIP_DB_TESTS = DATABASE_URL is None


def _get_column_default(conn, table: str, column: str) -> str | None:
    """查询指定列的 DEFAULT 值。"""
    sql = """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (table, column))
        row = cur.fetchone()
    if row is None:
        return None
    return row["column_default"]


def _index_exists(conn, index_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = %s
            ) AS exists
            """,
            (index_name,),
        )
        row = cur.fetchone()
    return bool(row["exists"])


class TestInitDbTimestampDefaults:
    """验证 init_db 确保 created_at / updated_at 有 DEFAULT NOW()"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from crawler.db import get_connection, init_db

        self.get_connection = get_connection
        self.init_db = init_db
        yield

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_articles_created_at_has_default_now(self):
        """articles.created_at 列应有 DEFAULT NOW()"""
        conn = self.get_connection()
        try:
            self.init_db(conn)
            default = _get_column_default(conn, "articles", "created_at")
            assert default is not None, "articles.created_at 不应有 NULL 默认值"
            assert "now()" in default.lower(), (
                f"articles.created_at 默认值应为 NOW()，实际为: {default}"
            )
        finally:
            conn.close()

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_articles_updated_at_has_default_now(self):
        """articles.updated_at 列应有 DEFAULT NOW()"""
        conn = self.get_connection()
        try:
            self.init_db(conn)
            default = _get_column_default(conn, "articles", "updated_at")
            assert default is not None, "articles.updated_at 不应有 NULL 默认值"
            assert "now()" in default.lower(), (
                f"articles.updated_at 默认值应为 NOW()，实际为: {default}"
            )
        finally:
            conn.close()

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_vectors_created_at_has_default_now(self):
        """vectors.created_at 列应有 DEFAULT NOW()"""
        conn = self.get_connection()
        try:
            self.init_db(conn)
            default = _get_column_default(conn, "vectors", "created_at")
            assert default is not None, "vectors.created_at 不应有 NULL 默认值"
            assert "now()" in default.lower(), (
                f"vectors.created_at 默认值应为 NOW()，实际为: {default}"
            )
        finally:
            conn.close()

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_vectors_updated_at_has_default_now(self):
        """vectors.updated_at 列应有 DEFAULT NOW()"""
        conn = self.get_connection()
        try:
            self.init_db(conn)
            default = _get_column_default(conn, "vectors", "updated_at")
            assert default is not None, "vectors.updated_at 不应有 NULL 默认值"
            assert "now()" in default.lower(), (
                f"vectors.updated_at 默认值应为 NOW()，实际为: {default}"
            )
        finally:
            conn.close()

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_insert_article_without_timestamps_fills_automatically(self):
        """不显式指定 created_at / updated_at 时，INSERT 后两列应自动填充"""
        from crawler.models import ArticleRecord
        from crawler.storage import ArticleRepository
        import uuid

        repo = ArticleRepository()
        unique = str(uuid.uuid4())[:8]
        link = f"https://example.com/test_defaults/{unique}"

        conn = self.get_connection()
        try:
            self.init_db(conn)
            record = ArticleRecord(
                title=f"默认值测试_{unique}",
                unit="测试",
                link=link,
                published_on="2026-04-09",
                content="正文",
                summary="摘要",
                attachments=[],
            )
            inserted, ids = repo.insert_articles(conn, [record], commit=True)
            assert inserted == 1

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT created_at, updated_at FROM articles WHERE link = %s",
                    (link,),
                )
                row = cur.fetchone()

            assert row["created_at"] is not None, "created_at 不应为 NULL"
            assert row["updated_at"] is not None, "updated_at 不应为 NULL"
            assert row["created_at"] <= datetime.now(tz=row["created_at"].tzinfo) + timedelta(seconds=5)
        finally:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM articles WHERE link = %s", (link,))
            conn.commit()
            conn.close()

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_init_db_idempotent(self):
        """重复调用 init_db 不应报错"""
        conn = self.get_connection()
        try:
            self.init_db(conn)
            self.init_db(conn)  # 第二次调用
            # 如果没抛异常就算通过
        finally:
            conn.close()

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_vectors_embedding_hnsw_index_exists_after_init_db(self):
        """init_db 执行后应创建 vectors.embedding 的 HNSW 索引"""
        conn = self.get_connection()
        try:
            self.init_db(conn)
            assert _index_exists(conn, "idx_vectors_embedding_hnsw")
        finally:
            conn.close()
