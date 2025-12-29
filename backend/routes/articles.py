"""文章API路由模块。

该模块提供文章相关的API端点，包括文章列表、详情查询等功能。
新缓存策略：articles:today（24h）、articles:page:{before_id}:{limit}（3天）
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, date, timezone
from typing import Any

from flask import Blueprint, jsonify, request, make_response, current_app

from backend.db import db_session
from backend.utils.redis_cache import get_cache

# 初始化蓝图
bp = Blueprint('articles', __name__)

# 设置日志
logger = logging.getLogger(__name__)

# 获取缓存实例
cache = get_cache()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    return value


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _serialize_value(val) for key, val in row.items()}


def _prefetch_next_page(before_id: int, limit: int):
    """异步预缓存下一页（线程安全版本）。

    使用独立的 Flask context 确保 DB/Redis 连接隔离。
    """
    # 在主线程中获取 app，避免子线程中 current_app 丢失
    from flask import current_app as app
    app = app._get_current_object()

    def prefetch():
        with app.app_context():
            try:
                cache_key = f"articles:page:{before_id}:{limit}"
                if cache and cache.exists(cache_key):
                    return

                sql = """
                    SELECT id, title, unit, link, published_on, summary, attachments, created_at
                    FROM articles
                    WHERE id < %s
                    ORDER BY id DESC
                    LIMIT %s
                """

                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(sql, (before_id, limit))
                    rows = cur.fetchall()

                if not rows:
                    return

                articles = [_serialize_row(row) for row in rows]
                next_before_id = articles[-1]['id']
                has_more = len(articles) == limit

                result = {
                    "articles": articles,
                    "next_before_id": next_before_id,
                    "has_more": has_more
                }

                if cache:
                    cache.set(cache_key, result, expire_seconds=259200)  # 3 days
                    logger.info(f"预缓存成功: {cache_key}")
            except Exception as e:
                logger.error(f"预缓存失败: {e}")

    thread = threading.Thread(target=prefetch, daemon=True)
    thread.start()


@bp.route('/today', methods=['GET'])
def get_today_articles():
    """获取当天所有文章（首页专用）。

    返回：
        {
            "articles": [...],  # 当天所有文章
            "next_before_id": 81,  # 当天最小 ID，用于加载更早的文章
            "has_more": true  # 是否存在更早的文章
        }
    """
    try:
        cache_key = "articles:today"

        # 尝试从缓存获取
        if cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                etag = cache.generate_etag(cached_data)
                if request.headers.get('If-None-Match') == etag:
                    return make_response('', 304)

                response = jsonify(cached_data)
                response.headers['ETag'] = etag
                response.headers['Cache-Control'] = 'max-age=3600, public'
                return response, 200

        # 查询当天所有文章
        today = datetime.now(timezone.utc).date().isoformat()
        sql = """
            SELECT id, title, unit, link, published_on, summary, attachments, created_at
            FROM articles
            WHERE published_on = %s
            ORDER BY id DESC
        """

        with db_session() as conn, conn.cursor() as cur:
            cur.execute(sql, (today,))
            rows = cur.fetchall()

        articles = [_serialize_row(row) for row in rows]

        # 准备响应数据
        next_before_id = articles[-1]['id'] if articles else None

        # 检查是否有历史文章（无论今天是否有文章）
        has_more = False
        with db_session() as conn, conn.cursor() as cur:
            if articles:
                # 今天有文章：检查是否存在 ID 更小的文章
                min_id = articles[-1]['id']
                cur.execute("SELECT EXISTS(SELECT 1 FROM articles WHERE id < %s) as has_more", (min_id,))
                result = cur.fetchone()
                has_more = result['has_more'] if result else False
            else:
                # 今天没有文章：查询数据库中最大ID作为分页起点
                cur.execute("SELECT MAX(id) as max_id FROM articles")
                result = cur.fetchone()
                next_before_id = result['max_id'] if result and result['max_id'] else None
                has_more = next_before_id is not None  # 有最大ID说明有历史文章

        response_data = {
            "articles": articles,
            "next_before_id": next_before_id,
            "has_more": has_more
        }

        # 缓存数据（24小时）
        if cache:
            cache.set(cache_key, response_data, expire_seconds=86400)

        etag = cache.generate_etag(response_data) if cache else ''
        response = jsonify(response_data)

        if etag:
            response.headers['ETag'] = etag
            response.headers['Cache-Control'] = 'max-age=3600, public'

        return response, 200

    except Exception as e:
        logger.error(f"获取当天文章失败: {e}")
        return jsonify({"error": "获取当天文章失败"}), 500


@bp.route('/', methods=['GET'])
def get_articles():
    """获取文章列表（分页）。

    查询参数：
        before_id: 加载 ID 小于此值的文章（必填）
        limit: 返回数量（可选，默认 20）

    返回：
        {
            "articles": [...],
            "next_before_id": 61,
            "has_more": true
        }
    """
    try:
        limit = min(int(request.args.get('limit', 20)), 100)  # 最多100篇
        before_id_str = request.args.get('before_id')

        # before_id 为必填参数
        if before_id_str is None:
            return jsonify({"error": "before_id 参数为必填，请使用 /today 端点获取首页数据"}), 400

        try:
            before_id = int(before_id_str)
        except ValueError:
            return jsonify({"error": "before_id 参数应为整数"}), 400

        # 生成缓存键（包含 limit）
        cache_key = f"articles:page:{before_id}:{limit}"

        # 尝试从缓存获取
        if cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                etag = cache.generate_etag(cached_data)
                if request.headers.get('If-None-Match') == etag:
                    return make_response('', 304)

                response = jsonify(cached_data)
                response.headers['ETag'] = etag
                response.headers['Cache-Control'] = 'max-age=3600, public'
                return response, 200

        # 构建SQL查询
        sql = """
            SELECT id, title, unit, link, published_on, summary, attachments, created_at
            FROM articles
            WHERE id < %s
            ORDER BY id DESC
            LIMIT %s
        """
        params = (before_id, limit)

        with db_session() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        articles = [_serialize_row(row) for row in rows]

        # 到底判断
        if not articles:
            response_data = {
                "articles": [],
                "next_before_id": None,
                "has_more": False
            }
        else:
            next_before_id = articles[-1]['id']
            has_more = len(articles) == limit
            response_data = {
                "articles": articles,
                "next_before_id": next_before_id,
                "has_more": has_more
            }

            # 异步预缓存下一页
            if has_more and cache:
                _prefetch_next_page(next_before_id, limit)

        # 缓存数据（3天）
        if cache:
            cache.set(cache_key, response_data, expire_seconds=259200)

        etag = cache.generate_etag(response_data) if cache else ''
        response = jsonify(response_data)

        if etag:
            response.headers['ETag'] = etag
            response.headers['Cache-Control'] = 'max-age=3600, public'

        return response, 200

    except Exception as e:
        logger.error(f"获取文章列表失败: {e}")
        return jsonify({"error": "获取文章列表失败"}), 500


@bp.route('/<int:article_id>', methods=['GET'])
def get_article_detail(article_id: int):
    """获取文章详情。

    根据文章ID获取完整的文章信息，包括内容和附件。
    实现了Redis缓存和304 Not Modified响应。

    参数：
        article_id: 文章ID

    返回：
        包含文章详情的JSON响应
    """
    try:
        # 生成缓存键
        cache_key = f"articles:detail:{article_id}"

        # 尝试从缓存获取
        if cache:
            cached_article = cache.get(cache_key)
            if cached_article:
                # 生成ETag
                etag = cache.generate_etag(cached_article)

                # 检查If-None-Match头
                if request.headers.get('If-None-Match') == etag:
                    return make_response('', 304)

                # 返回缓存数据
                response = jsonify(cached_article)
                response.headers['ETag'] = etag
                response.headers['Cache-Control'] = 'max-age=3600, public'
                return response, 200

        sql = """
        SELECT id, title, unit, link, published_on, content, summary, attachments, created_at, updated_at
        FROM articles
        WHERE id = %s
        """

        with db_session() as conn, conn.cursor() as cur:
            cur.execute(sql, (article_id,))
            article = cur.fetchone()

        if not article:
            return jsonify({"error": "文章不存在"}), 404

        article_data = _serialize_row(article)

        # 缓存数据（3天）
        if cache:
            cache.set(cache_key, article_data, expire_seconds=259200)

        # 生成ETag并返回响应
        etag = cache.generate_etag(article_data) if cache else ''
        response = jsonify(article_data)

        if etag:
            response.headers['ETag'] = etag
            response.headers['Cache-Control'] = 'max-age=3600, public'

        return response, 200

    except Exception as e:
        logger.error(f"获取文章详情失败: {e}")
        return jsonify({"error": "获取文章详情失败"}), 500
