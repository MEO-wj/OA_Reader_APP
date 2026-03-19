"""OA 爬虫数据库操作模块。

该模块提供了与 PostgreSQL 数据库交互的功能，包括：
- 数据库连接管理
- 表结构初始化（文章表和向量表）
- 文章数据的增删查改
- 向量数据的存储和查询
- 事务管理

使用 psycopg 库操作 PostgreSQL 数据库，并支持 pgvector 扩展用于向量存储。
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from crawler.config import Config
from crawler.models import ArticleRecord


def get_connection() -> psycopg.Connection:
    """获取数据库连接。
    
    返回：
        psycopg.Connection: 数据库连接对象
        
    异常：
        RuntimeError: 当 DATABASE_URL 未配置时抛出
    """
    cfg = Config()
    if not cfg.database_url:
        raise RuntimeError("DATABASE_URL 未配置，无法连接数据库")
    # 添加连接超时设置（5秒）
    return psycopg.connect(cfg.database_url, row_factory=dict_row, connect_timeout=5)


def init_db(conn: psycopg.Connection) -> None:
    """初始化数据库表结构（如果不存在）。
    
    创建所需的表和扩展：
    - vector 扩展：用于存储和查询向量
    - articles 表：存储文章信息
    - vectors 表：存储文章向量（仅当日文章）
    
    参数：
        conn: 数据库连接对象
    """
    dim = Config().embed_dim  # 获取配置的向量维度
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector;",  # 创建向量扩展
        """
        CREATE TABLE IF NOT EXISTS articles (
            id BIGSERIAL PRIMARY KEY,              -- 文章ID，自增主键
            title TEXT NOT NULL,                   -- 文章标题
            unit TEXT,                             -- 发布单位
            link TEXT NOT NULL UNIQUE,             -- 文章链接（唯一约束）
            published_on DATE NOT NULL,            -- 发布日期
            content TEXT NOT NULL,                 -- 文章内容
            summary TEXT NOT NULL,                 -- 文章摘要
            attachments JSONB DEFAULT '[]'::jsonb, -- 附件信息（JSON格式）
            created_at TIMESTAMPTZ DEFAULT NOW(),  -- 创建时间
            updated_at TIMESTAMPTZ DEFAULT NOW()   -- 更新时间
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_articles_published_on ON articles (published_on);",  #-- 发布日期索引
        f"""
        CREATE TABLE IF NOT EXISTS vectors (
            id BIGSERIAL PRIMARY KEY,              -- 向量ID，自增主键
            article_id BIGINT REFERENCES articles(id) ON DELETE CASCADE,  -- 关联的文章ID
            embedding vector({dim}),               -- 向量数据，维度从配置获取
            published_on DATE NOT NULL,            -- 发布日期
            created_at TIMESTAMPTZ DEFAULT NOW(),  -- 创建时间
            updated_at TIMESTAMPTZ DEFAULT NOW()   -- 更新时间
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_vectors_published_on ON vectors (published_on);",  #-- 发布日期索引
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_vectors_article ON vectors(article_id);",  #-- 文章ID唯一索引
    ]
    
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()


def fetch_existing_links(conn: psycopg.Connection, target_date: str) -> set[str]:
    """获取指定日期已存在的文章链接集合，用于增量爬取去重。
    
    参数：
        conn: 数据库连接对象
        target_date: 目标日期，格式为 YYYY-MM-DD
        
    返回：
        set[str]: 已存在的文章链接集合
    """
    sql = "SELECT link FROM articles WHERE published_on = %s"  # 查询指定日期的所有链接
    with conn.cursor() as cur:
        cur.execute(sql, (target_date,))
        rows = cur.fetchall()
    return {row["link"] for row in rows}  # 转换为集合返回


def insert_articles(conn: psycopg.Connection, records: Iterable[ArticleRecord], commit: bool = True) -> int:
    """批量插入文章记录，已存在的链接会被忽略（基于UNIQUE约束）。

    参数：
        conn: 数据库连接对象
        records: ArticleRecord 对象的可迭代集合
        commit: 是否立即提交，False 时由调用方控制事务

    返回：
        int: 成功插入的记录数
    """
    sql = """
    INSERT INTO articles (title, unit, link, published_on, content, summary, attachments)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (link) DO NOTHING  -- 链接冲突时忽略
    """

    count = 0
    with conn.cursor() as cur:
        for rec in records:
            cur.execute(
                sql,
                (
                    rec.title,          # 文章标题
                    rec.unit,           # 发布单位
                    rec.link,           # 文章链接
                    rec.published_on,   # 发布日期
                    rec.content,        # 文章内容
                    rec.summary,        # 文章摘要
                    Json(rec.attachments),  # 附件信息（转换为JSONB）
                ),
            )
            count += cur.rowcount  # 累加受影响的行数

    if commit:
        conn.commit()
    return count


def fetch_article_ids(conn: psycopg.Connection, links: list[str]) -> list[dict[str, Any]]:
    """根据文章链接批量获取文章ID和相关信息。
    
    参数：
        conn: 数据库连接对象
        links: 文章链接列表
        
    返回：
        list[dict[str, Any]]: 包含文章ID和相关信息的字典列表
    """
    if not links:
        return []
    
    sql = "SELECT id, link, title, summary, content, published_on FROM articles WHERE link = ANY(%s)"
    with conn.cursor() as cur:
        cur.execute(sql, (links,))
        rows = cur.fetchall()
    
    return list(rows)


def fetch_articles_by_date(conn: psycopg.Connection, target_date: str) -> list[dict[str, Any]]:
    """获取指定日期的完整文章信息（用于缓存预热）。"""
    sql = """
    SELECT id, title, unit, link, published_on, summary, attachments, created_at, updated_at, content
    FROM articles
    WHERE published_on = %s
    ORDER BY created_at DESC, id DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (target_date,))
        rows = cur.fetchall()
    return list(rows)


def insert_embeddings(conn: psycopg.Connection, payloads: Iterable[dict[str, Any]], commit: bool = True) -> int:
    """批量插入文章向量记录，已存在的article_id会被忽略。

    参数：
        conn: 数据库连接对象
        payloads: 向量数据字典的可迭代集合，每个字典包含：
                  - article_id: 文章ID
                  - embedding: 向量数据
                  - published_on: 发布日期
        commit: 是否立即提交，False 时由调用方控制事务

    返回：
        int: 成功插入的记录数
    """
    sql = """
    INSERT INTO vectors (article_id, embedding, published_on)
    VALUES (%(article_id)s, %(embedding)s::vector, %(published_on)s)
    ON CONFLICT (article_id) DO NOTHING  -- article_id冲突时忽略
    """

    count = 0
    with conn.cursor() as cur:
        for item in payloads:
            cur.execute(sql, item)
            count += cur.rowcount  # 累加受影响的行数

    if commit:
        conn.commit()
    return count


@contextlib.contextmanager
def db_session():
    """数据库会话上下文管理器，自动管理连接的创建和关闭。
    
    使用方式：
        with db_session() as conn:
            # 执行数据库操作
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
