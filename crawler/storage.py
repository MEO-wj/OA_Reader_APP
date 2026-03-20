"""OA 系统文章数据仓库。

该模块提供了一个封装数据库操作的仓库类，用于管理文章数据的存储和检索。
它作为一个代理层，将所有数据库操作转发给 db.py 模块中的具体实现，
实现了业务逻辑与数据访问层的解耦。
"""

from __future__ import annotations

from typing import Any, Iterable, List

import psycopg

from crawler.db import (
    fetch_article_ids,
    fetch_articles_by_date,
    fetch_existing_links,
    init_db,
    insert_articles,
    insert_embeddings,
)
from crawler.models import ArticleRecord


class ArticleRepository:
    """基于 PostgreSQL 的文章数据仓库类。
    
    该类封装了所有与数据库相关的操作，提供了简洁的接口给业务逻辑层使用。
    它作为一个代理，将所有操作转发给 db.py 模块中的具体实现。
    """

    def __init__(self) -> None:
        """初始化文章数据仓库实例。"""
        pass

    def ensure_schema(self, conn: psycopg.Connection) -> None:
        """确保数据库表结构存在。
        
        参数：
            conn: 数据库连接对象
        """
        init_db(conn)

    def existing_links(self, conn: psycopg.Connection, target_date: str) -> set[str]:
        """获取指定日期已存在的文章链接集合（用于去重）。
        
        参数：
            conn: 数据库连接对象
            target_date: 目标日期，格式为 YYYY-MM-DD
            
        返回：
            set[str]: 已存在的文章链接集合
        """
        return fetch_existing_links(conn, target_date)

    def insert_articles(
        self,
        conn: psycopg.Connection,
        records: Iterable[ArticleRecord],
        commit: bool = True,
    ) -> tuple[int, list[int]]:
        """批量插入文章数据。

        参数：
            conn: 数据库连接对象
            records: 文章记录迭代器
            commit: 是否立即提交，False 时由调用方控制事务

        返回：
            tuple[int, list[int]]: (成功插入数, 新插入文章ID列表)
        """
        return insert_articles(conn, records, commit=commit)

    def fetch_for_embedding(self, conn: psycopg.Connection, links: List[str]) -> List[dict[str, Any]]:
        """根据链接获取文章ID等信息，用于后续向量生成。
        
        参数：
            conn: 数据库连接对象
            links: 文章链接列表
            
        返回：
            List[dict[str, Any]]: 包含文章ID、标题、摘要、正文等信息的列表
        """
        return fetch_article_ids(conn, links)

    def insert_embeddings(self, conn: psycopg.Connection, payloads: Iterable[dict[str, Any]], commit: bool = True) -> int:
        """批量插入文章向量数据。

        参数：
            conn: 数据库连接对象
            payloads: 向量数据迭代器
            commit: 是否立即提交，False 时由调用方控制事务

        返回：
            int: 成功插入的向量数
        """
        return insert_embeddings(conn, payloads, commit=commit)

    def fetch_for_cache(self, conn: psycopg.Connection, target_date: str) -> List[dict[str, Any]]:
        """获取指定日期的文章列表与详情，用于Redis缓存预热。"""
        return fetch_articles_by_date(conn, target_date)
