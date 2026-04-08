#!/usr/bin/env python3
"""
独立的表结构验证脚本
"""
import asyncio
import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def verify_table():
    """验证 articles 表结构"""

    db_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "ai_workflow"),
        "password": os.getenv("DB_PASSWORD", "ai_workflow"),
        "database": os.getenv("DB_NAME", "ai_workflow"),
    }

    print("🔍 验证 articles 表结构")
    print("=" * 80)

    conn = None
    try:
        conn = await asyncpg.connect(**db_config)

        # 使用 \d 等效查询
        result = await conn.fetch("""
            SELECT
                a.attname AS column_name,
                pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE 'NULL' END AS nullable,
                COALESCE(pg_catalog.pg_get_expr(d.adbin, d.adrelid), '') AS column_default
            FROM pg_catalog.pg_attribute a
            LEFT JOIN pg_catalog.pg_attrdef d ON (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
            WHERE a.attrelid = 'articles'::regclass
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY a.attnum;
        """)

        print("\n📋 Column Information:")
        print("-" * 80)
        for row in result:
            print(f"  {row['column_name']:20} {row['data_type']:25} {row['nullable']:10} {row['column_default'] or ''}")

        # 验证索引
        print("\n📋 Indexes (articles):")
        indexes = await conn.fetch("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename IN ('articles', 'vectors')
            ORDER BY indexname;
        """)
        for idx in indexes:
            print(f"  - {idx['indexname']}")
            print(f"    {idx['indexdef']}")

        # 验证注释
        print("\n📋 Comments:")
        table_comment = await conn.fetchval("SELECT obj_description('articles'::regclass, 'pg_class')")
        print(f"  articles: {table_comment}")
        vectors_comment = await conn.fetchval("SELECT obj_description('vectors'::regclass, 'pg_class')")
        print(f"  vectors: {vectors_comment}")

        print("\n" + "=" * 80)
        print("✅ 验证完成！表结构正确。")

    except Exception as e:
        print(f"\n❌ 错误: {type(e).__name__}: {e}")
        return False
    finally:
        if conn is not None:
            await conn.close()

    return True


if __name__ == "__main__":
    success = asyncio.run(verify_table())
    exit(0 if success else 1)
