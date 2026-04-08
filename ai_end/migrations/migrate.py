#!/usr/bin/env python3
"""
迁移执行脚本
使用 asyncpg 执行 SQL 迁移文件
"""
import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

SCHEMA_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW()
);
"""

SELECT_APPLIED_MIGRATIONS_SQL = """
SELECT version FROM schema_migrations ORDER BY version;
"""

INSERT_APPLIED_MIGRATION_SQL = """
INSERT INTO schema_migrations (version)
VALUES ($1)
ON CONFLICT (version) DO NOTHING;
"""

MIGRATION_LOCK_ID = 20260301


async def _has_schema_drift(conn: asyncpg.Connection) -> bool:
    """
    检测核心表/字段是否缺失（简化版）。

    目标：当库被手工修改导致缺表/缺字段时，触发修复迁移。
    """
    checks = [
        ("articles", "id"),
        ("articles", "title"),
        ("articles", "content"),
        ("articles", "summary"),
        ("vectors", "id"),
        ("vectors", "article_id"),
        ("vectors", "embedding"),
        ("skills", "id"),
        ("skills", "name"),
        ("skills", "metadata"),
        ("skills", "content"),
        ("skill_references", "id"),
        ("skill_references", "skill_id"),
        ("skill_references", "file_path"),
        ("skill_references", "content"),
        ("conversations", "id"),
        ("conversations", "user_id"),
        ("conversations", "conversation_id"),
        ("conversations", "title"),
        ("conversations", "messages"),
        ("conversations", "updated_at"),
        ("conversation_sessions", "id"),
        ("conversation_sessions", "user_id"),
        ("conversation_sessions", "conversation_id"),
        ("conversation_sessions", "updated_at"),
        ("user_profiles", "id"),
        ("user_profiles", "user_id"),
    ]

    for table_name, column_name in checks:
        exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = $1
                  AND column_name = $2
            );
            """,
            table_name,
            column_name,
        )
        if not exists:
            return True

    uuid_type_checks = [
        ("conversations", "user_id", "uuid"),
        ("conversation_sessions", "user_id", "uuid"),
        ("user_profiles", "user_id", "uuid"),
    ]

    for table_name, column_name, expected_type in uuid_type_checks:
        data_type = await conn.fetchval(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
              AND column_name = $2
            """,
            table_name,
            column_name,
        )
        if data_type != expected_type:
            return True

    return False


async def _apply_schema_repair(conn: asyncpg.Connection) -> None:
    """
    执行幂等修复 SQL（缺表/缺字段场景）。
    """
    repair_sql_list = [
        "CREATE EXTENSION IF NOT EXISTS vector;",
        "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
        """
        CREATE TABLE IF NOT EXISTS articles (
            id BIGSERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            unit TEXT,
            link TEXT NOT NULL UNIQUE,
            published_on DATE NOT NULL,
            content TEXT NOT NULL,
            summary TEXT NOT NULL,
            attachments JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_articles_published_on ON articles (published_on);",
        "CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops);",
        "CREATE INDEX IF NOT EXISTS idx_articles_content_trgm ON articles USING gin (content gin_trgm_ops);",
        "COMMENT ON TABLE articles IS 'OA文章表';",
        """
        CREATE TABLE IF NOT EXISTS vectors (
            id BIGSERIAL PRIMARY KEY,
            article_id BIGINT REFERENCES articles(id) ON DELETE CASCADE,
            embedding vector(1024),
            published_on DATE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_vectors_published_on ON vectors (published_on);",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_vectors_article ON vectors(article_id);",
        "CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw ON vectors USING hnsw (embedding vector_cosine_ops);",
        "COMMENT ON TABLE vectors IS '文章向量表';",
        """
        CREATE TABLE IF NOT EXISTS skills (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            verification_token VARCHAR(100),
            metadata JSONB NOT NULL DEFAULT '{}',
            content TEXT NOT NULL,
            tools TEXT,
            is_static BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'skill_references'
                  AND column_name = 'filename'
            ) AND NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'skill_references'
                  AND column_name = 'file_path'
            ) THEN
                ALTER TABLE skill_references RENAME COLUMN filename TO file_path;
            END IF;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS skill_references (
            id SERIAL PRIMARY KEY,
            skill_id INTEGER REFERENCES skills(id) ON DELETE CASCADE,
            file_path VARCHAR(500) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(skill_id, file_path)
        );
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'conversations'
                  AND column_name = 'user_id'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE conversations ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
            END IF;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            conversation_id VARCHAR(64) NOT NULL,
            title VARCHAR(256) DEFAULT '新会话',
            messages JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'conversation_sessions'
                  AND column_name = 'user_id'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE conversation_sessions ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
            END IF;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            conversation_id VARCHAR(64) NOT NULL,
            title VARCHAR(256) DEFAULT '新会话',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'user_profiles'
                  AND column_name = 'user_id'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE user_profiles ALTER COLUMN user_id TYPE UUID USING user_id::uuid;
            END IF;
        END $$;
        """,
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id SERIAL PRIMARY KEY,
            user_id UUID UNIQUE NOT NULL,
            portrait_text TEXT,
            knowledge_text TEXT,
            preferences JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_user_conv ON conversations(user_id, conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_user_conv ON conversation_sessions(user_id, conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON conversation_sessions(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);",
    ]

    async with conn.transaction():
        for stmt in repair_sql_list:
            await conn.execute(stmt)


async def run_migration(auto_repair: bool = False):
    """执行迁移脚本"""

    # 数据库连接配置
    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "ai_workflow"),
        "password": os.getenv("DB_PASSWORD", "ai_workflow"),
        "database": os.getenv("DB_NAME", "ai_workflow"),
    }

    migrations_dir = Path(__file__).parent
    migration_files = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql"))
    if not migration_files:
        print("❌ 未找到可执行的迁移文件")
        return False

    print(f"📦 正在连接数据库: {db_config['user']}@{db_config['host']}:{db_config['port']}/{db_config['database']}")

    conn = None
    try:
        # 连接数据库
        conn = await asyncpg.connect(**db_config)
        print("✅ 数据库连接成功")
        await conn.execute("SELECT pg_advisory_lock($1);", MIGRATION_LOCK_ID)

        # 初始化迁移记录表，并读取已应用迁移
        await conn.execute(SCHEMA_MIGRATIONS_TABLE_SQL)
        applied_rows = await conn.fetch(SELECT_APPLIED_MIGRATIONS_SQL)
        applied_versions = {row["version"] for row in applied_rows}

        for migration_file in migration_files:
            if migration_file.name in applied_versions:
                print(f"⏭️  跳过已执行迁移: {migration_file.name}")
                continue

            # 读取迁移文件
            with open(migration_file, "r", encoding="utf-8") as f:
                migration_sql = f.read()

            print(f"📄 执行迁移文件: {migration_file.name}")

            # 每个迁移文件独立事务，保证单文件原子性
            async with conn.transaction():
                await conn.execute(migration_sql)
                await conn.execute(INSERT_APPLIED_MIGRATION_SQL, migration_file.name)
            print("✅ 迁移执行成功")

        if auto_repair:
            drift_before = await _has_schema_drift(conn)
            if drift_before:
                print("⚠️ 检测到 schema 漂移，正在执行自动修复...")
                await _apply_schema_repair(conn)
                drift_after = await _has_schema_drift(conn)
                if drift_after:
                    print("❌ 自动修复后仍存在 schema 漂移")
                    return False
                print("✅ schema 自动修复完成")

        # 验证表创建
        print("\n🔍 验证表结构...")
        table_info = await conn.fetch("""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name IN ('articles', 'vectors')
            ORDER BY table_name, ordinal_position;
        """)

        if table_info:
            print("\n📋 articles + vectors 表结构:")
            print("-" * 80)
            for col in table_info:
                print(f"  {col['column_name']:20} | {col['data_type']:20} | NULL: {col['is_nullable']:5} | DEFAULT: {col['column_default'] or '-'}")
            print("-" * 80)
        else:
            print("❌ 未找到 articles 或 vectors 表")

        # 验证索引
        print("\n🔍 验证索引...")
        indexes = await conn.fetch("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename IN ('articles', 'vectors');
        """)

        if indexes:
            print("\n📋 articles + vectors 表索引:")
            print("-" * 80)
            for idx in indexes:
                print(f"  {idx['indexname']}")
                print(f"    定义: {idx['indexdef']}")
            print("-" * 80)
        else:
            print("❌ 未找到索引")

        # 验证 pgvector 扩展
        print("\n🔍 验证 pgvector 扩展...")
        ext = await conn.fetchval("""
            SELECT extname FROM pg_extension WHERE extname = 'vector';
        """)

        if ext:
            print(f"✅ pgvector 扩展已安装")
        else:
            print("❌ pgvector 扩展未安装")

        # 验证 pg_trgm 扩展
        print("\n🔍 验证 pg_trgm 扩展...")
        ext_trgm = await conn.fetchval("""
            SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';
        """)

        if ext_trgm:
            print(f"✅ pg_trgm 扩展已安装")
        else:
            print("❌ pg_trgm 扩展未安装")

        # 验证注释
        print("\n🔍 验证表和列注释...")
        for tbl in ['articles', 'vectors']:
            table_comment = await conn.fetchval(f"""
                SELECT obj_description('{tbl}'::regclass, 'pg_class');
            """)
            print(f"  {tbl} 表注释: {table_comment or '(无)'}")

        column_comments = await conn.fetch("""
            SELECT
                a.attname AS column_name,
                pgd.description
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = c.oid AND pgd.objsubid = a.attnum
            WHERE c.relname IN ('articles', 'vectors')
                AND n.nspname = 'public'
                AND a.attnum > 0
                AND NOT a.attisdropped
                AND pgd.description IS NOT NULL
            ORDER BY c.relname, a.attnum;
        """)

        if column_comments:
            print("  列注释:")
            for cc in column_comments:
                print(f"    {cc['column_name']}: {cc['description']}")
        else:
            print("  (无列注释)")

    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {e}")
        return False
    finally:
        if conn is not None:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1);", MIGRATION_LOCK_ID)
            except Exception:
                pass
            await conn.close()
            print("\n👋 数据库连接已关闭")

    return True


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    exit(0 if success else 1)
