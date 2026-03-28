"""迁移脚本测试"""
from pathlib import Path

import pytest

from migrations import migrate


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        self.conn.transaction_enters += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.transaction_exits += 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False


class FakeConn:
    def __init__(
        self,
        applied_versions: set[str] | None = None,
        fail_on_sql: str | None = None,
    ):
        self.applied_versions = applied_versions or set()
        self.fail_on_sql = fail_on_sql
        self.executed_sql: list[str] = []
        self.inserted_versions: list[str] = []
        self.transaction_enters = 0
        self.transaction_exits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0

    def transaction(self):
        return FakeTransaction(self)

    async def execute(self, sql: str, *args):
        self.executed_sql.append(sql)
        if self.fail_on_sql and sql == self.fail_on_sql:
            raise Exception("boom")
        if "INSERT INTO schema_migrations" in sql:
            self.inserted_versions.append(args[0])

    async def fetch(self, query: str, *args):
        if "FROM schema_migrations" in query:
            return [{"version": version} for version in sorted(self.applied_versions)]
        return []

    async def fetchval(self, query: str):
        return None

    async def close(self):
        return None


def _migration_files() -> list[Path]:
    migrations_dir = Path(migrate.__file__).parent
    return sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))


def _migration_sql_contents(files: list[Path]) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in files]


@pytest.mark.asyncio
async def test_run_migration_executes_all_sql_files_in_order(monkeypatch):
    """无历史记录时应按顺序执行全部迁移。"""
    fake_conn = FakeConn()

    async def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)

    success = await migrate.run_migration()

    expected_files = _migration_files()
    expected_sql = _migration_sql_contents(expected_files)

    executed_migration_sql = [sql for sql in fake_conn.executed_sql if sql in expected_sql]

    assert success is True
    assert executed_migration_sql == expected_sql
    assert fake_conn.inserted_versions == [f.name for f in expected_files]


@pytest.mark.asyncio
async def test_run_migration_skips_applied_files(monkeypatch):
    """已记录的迁移文件应跳过，不重复执行。"""
    all_files = _migration_files()
    already_applied = {all_files[0].name}
    fake_conn = FakeConn(applied_versions=already_applied)

    async def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)

    success = await migrate.run_migration()

    expected_sql = _migration_sql_contents(all_files[1:])
    executed_migration_sql = [sql for sql in fake_conn.executed_sql if sql in _migration_sql_contents(all_files)]

    assert success is True
    assert executed_migration_sql == expected_sql
    assert fake_conn.inserted_versions == [f.name for f in all_files[1:]]


@pytest.mark.asyncio
async def test_run_migration_stops_and_rolls_back_on_failure(monkeypatch):
    """某个迁移失败时应停止后续迁移，并触发回滚语义。"""
    all_files = _migration_files()
    all_sql = _migration_sql_contents(all_files)

    # 当只有一个迁移文件时，无法测试"第二个失败后停止"，改为测试第一个失败
    if len(all_sql) < 2:
        # 单文件场景：测试失败处理
        fail_sql = all_sql[0]
        fake_conn = FakeConn(fail_on_sql=fail_sql)

        async def fake_connect(**kwargs):
            return fake_conn

        monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)

        success = await migrate.run_migration()

        executed_migration_sql = [sql for sql in fake_conn.executed_sql if sql in all_sql]

        assert success is False
        assert executed_migration_sql == [all_sql[0]]
        assert fake_conn.inserted_versions == []
        assert fake_conn.transaction_rollbacks >= 1
        return

    # 多文件场景：原始测试逻辑
    fail_sql = all_sql[1]
    fake_conn = FakeConn(fail_on_sql=fail_sql)

    async def fake_connect(**kwargs):
        return fake_conn

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)

    success = await migrate.run_migration()

    executed_migration_sql = [sql for sql in fake_conn.executed_sql if sql in all_sql]

    assert success is False
    assert executed_migration_sql == [all_sql[0], fail_sql]
    assert fake_conn.inserted_versions == [all_files[0].name]
    assert fake_conn.transaction_rollbacks >= 1


@pytest.mark.asyncio
async def test_run_migration_auto_repair_when_schema_drift_detected(monkeypatch):
    """auto_repair=True 且检测到 schema 漂移时，应触发修复流程。"""
    fake_conn = FakeConn()

    async def fake_connect(**kwargs):
        return fake_conn

    drift_calls = {"count": 0}

    async def fake_has_drift(_conn):
        drift_calls["count"] += 1
        return drift_calls["count"] == 1

    repaired = {"called": False}

    async def fake_repair(_conn):
        repaired["called"] = True

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(migrate, "_has_schema_drift", fake_has_drift)
    monkeypatch.setattr(migrate, "_apply_schema_repair", fake_repair)

    success = await migrate.run_migration(auto_repair=True)

    assert success is True
    assert repaired["called"] is True
    assert drift_calls["count"] == 2


@pytest.mark.asyncio
async def test_schema_drift_check_targets_generic_tables():
    """
    契约测试：_has_schema_drift 的 checks 列表必须覆盖目标通用表集合
    （documents/skills/skill_references/conversations/
    conversation_sessions/user_profiles）。

    注意：本测试仅验证“表覆盖”是否完整，不做列级断言。
    """
    # 目标通用表集合（此处仅用于表名覆盖断言）
    expected_generic_tables = {
        "articles": ["id", "title", "content", "summary"],
        "vectors": ["id", "article_id", "embedding"],
        "skills": ["id", "name", "description", "verification_token"],
        "skill_references": ["id", "skill_id", "file_path", "content"],
        "conversations": ["id", "user_id", "conversation_id", "title", "messages", "updated_at"],
        "conversation_sessions": ["id", "user_id", "conversation_id", "updated_at"],
        "user_profiles": ["id", "user_id"],
    }

    # 读取 migrate.py 源码中的 checks 列表
    import inspect

    source = inspect.getsource(migrate._has_schema_drift)
    # 从源码中提取检查的表名
    import re

    checked_tables = set()
    for line in source.split("\n"):
        # 匹配 ("table_name", "column_name") 模式
        match = re.search(r'\("(\w+)",\s*"(\w+)"\)', line)
        if match:
            checked_tables.add(match.group(1))

    # 断言：必须包含所有目标通用表
    for table in expected_generic_tables:
        assert table in checked_tables, f"缺少目标表检查: {table}"


@pytest.mark.asyncio
async def test_apply_schema_repair_handles_legacy_skill_references_column():
    """auto_repair 应能处理 skill_references.filename -> file_path 的兼容修复。"""
    fake_conn = FakeConn()

    await migrate._apply_schema_repair(fake_conn)

    executed_sql = "\n".join(fake_conn.executed_sql).lower()
    assert "alter table skill_references" in executed_sql
    assert "file_path" in executed_sql


@pytest.mark.asyncio
async def test_apply_schema_repair_adds_articles_content_trgm_index():
    """auto_repair 应补齐 articles.content 的 pg_trgm 索引，避免关键词检索退化。"""
    fake_conn = FakeConn()

    await migrate._apply_schema_repair(fake_conn)

    executed_sql = "\n".join(fake_conn.executed_sql).lower()
    assert "idx_articles_content_trgm" in executed_sql
    assert "gin_trgm_ops" in executed_sql
    assert "articles" in executed_sql
    assert "content" in executed_sql


@pytest.mark.asyncio
async def test_apply_schema_repair_adds_vectors_embedding_index():
    """auto_repair 应补齐 vectors.embedding 的 HNSW 向量索引。"""
    fake_conn = FakeConn()

    await migrate._apply_schema_repair(fake_conn)

    executed_sql = "\n".join(fake_conn.executed_sql).lower()
    assert "idx_vectors_embedding_hnsw" in executed_sql
    assert "using hnsw" in executed_sql
    assert "vector_cosine_ops" in executed_sql


@pytest.mark.asyncio
async def test_apply_schema_repair_adds_vectors_article_index():
    """auto_repair 应补齐 vectors.article_id 的唯一索引，保持与基线一致。"""
    fake_conn = FakeConn()

    await migrate._apply_schema_repair(fake_conn)

    executed_sql = "\n".join(fake_conn.executed_sql).lower()
    assert "idx_vectors_article" in executed_sql
    assert "on vectors(article_id)" in executed_sql


def test_baseline_migration_contains_articles_content_trgm_index():
    """基线迁移文件应包含 articles.content 的 pg_trgm 索引定义。"""
    migrations_dir = Path(migrate.__file__).parent
    baseline = migrations_dir / "001_init_generic_backend.sql"
    content = baseline.read_text(encoding="utf-8").lower()

    assert "idx_articles_content_trgm" in content
    assert "articles using gin (content gin_trgm_ops)" in content.replace("\n", " ")
