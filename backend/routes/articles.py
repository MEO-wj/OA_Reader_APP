"""文章API路由模块。

该模块提供文章相关的API端点，包括文章列表、详情查询等功能。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime, date, timezone
from typing import Any

from flask import Blueprint, jsonify, make_response, request

from backend.db import db_session

# 初始化蓝图
bp = Blueprint('articles', __name__)

# 设置日志
logger = logging.getLogger(__name__)


def _generate_etag(value: Any) -> str:
    """生成内容的ETag"""
    if isinstance(value, (dict, list)):
        content = json.dumps(value, sort_keys=True, ensure_ascii=False)
    else:
        content = str(value)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _build_conditional_response(payload: Any) -> tuple[Any, int]:
    """根据 ETag/If-None-Match 构造条件响应。"""
    etag = _generate_etag(payload)
    if etag and request.if_none_match.contains(etag):
        response = make_response("", 304)
    else:
        response = make_response(jsonify(payload), 200)

    if etag:
        response.headers['ETag'] = etag
        response.headers['Cache-Control'] = 'max-age=3600, public'
    return response, response.status_code


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


def _prefetch_next_page_v1(before_id: int, limit: int):
    """异步预缓存下一页（v1，仅 before_id 版本）。

    使用独立的 Flask context 确保 DB/Redis 连接隔离。
    """
    # 在主线程中获取 app，避免子线程中 current_app 丢失
    from flask import current_app as app
    app = app._get_current_object()

    def prefetch():
        with app.app_context():
            try:
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
                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM articles WHERE id < %s) as has_more",
                        (next_before_id,)
                    )
                    result = cur.fetchone()
                    has_more = result['has_more'] if result else False

                result = {
                    "articles": articles,
                    "next_before_id": next_before_id,
                    "has_more": has_more
                }

            except Exception as e:
                logger.error(f"预缓存失败: {e}")

    thread = threading.Thread(target=prefetch, daemon=True)
    thread.start()


def _prefetch_next_page_v2(before_date: date, before_id: int, limit: int):
    """异步预缓存下一页（v2，before_date + before_id 版本）。

    使用独立的 Flask context 确保 DB/Redis 连接隔离。
    """
    # 在主线程中获取 app，避免子线程中 current_app 丢失
    from flask import current_app as app
    app = app._get_current_object()

    def prefetch():
        with app.app_context():
            try:
                sql = """
                    SELECT id, title, unit, link, published_on, summary, attachments, created_at
                    FROM articles
                    WHERE (published_on < %s)
                       OR (published_on = %s AND id < %s)
                    ORDER BY published_on DESC, id DESC
                    LIMIT %s
                """

                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(sql, (before_date, before_date, before_id, limit))
                    rows = cur.fetchall()

                if not rows:
                    return

                articles = [_serialize_row(row) for row in rows]
                next_before_date = rows[-1]['published_on']
                next_before_id = rows[-1]['id']
                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT EXISTS(
                            SELECT 1 FROM articles
                            WHERE (published_on < %s)
                               OR (published_on = %s AND id < %s)
                        ) as has_more
                        """,
                        (next_before_date, next_before_date, next_before_id)
                    )
                    result = cur.fetchone()
                    has_more = result['has_more'] if result else False

                result = {
                    "articles": articles,
                    "next_before_date": next_before_date.isoformat() if next_before_date else None,
                    "next_before_id": next_before_id,
                    "has_more": has_more
                }

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
            "next_before_date": "2025-01-15",  # 下一页游标日期
            "next_before_id": 81,  # 当天最小 ID，用于加载更早的文章
            "has_more": true  # 是否存在更早的文章
        }
    """
    try:
        # 查询当天所有文章
        today = datetime.now(timezone.utc).date().isoformat()
        sql = """
            SELECT id, title, unit, link, published_on, summary, attachments, created_at
            FROM articles
            WHERE published_on = %s
            ORDER BY published_on DESC, id DESC
        """

        with db_session() as conn, conn.cursor() as cur:
            cur.execute(sql, (today,))
            rows = cur.fetchall()

        articles = [_serialize_row(row) for row in rows]

        # 准备响应数据
        next_before_date = today if articles else None
        next_before_id = articles[-1]['id'] if articles else None

        # 检查是否有历史文章（无论今天是否有文章）
        has_more = False
        with db_session() as conn, conn.cursor() as cur:
            if articles:
                # 今天有文章：检查是否存在更早日期的文章
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM articles WHERE published_on < %s) as has_more",
                    (today,)
                )
                result = cur.fetchone()
                has_more = result['has_more'] if result else False
            else:
                # 今天没有文章：以最近发布日期作为分页起点
                cur.execute("SELECT MAX(published_on) as max_date FROM articles")
                result = cur.fetchone()
                if result and result['max_date']:
                    max_date = result['max_date']
                    cur.execute(
                        "SELECT MAX(id) as max_id FROM articles WHERE published_on = %s",
                        (max_date,)
                    )
                    id_result = cur.fetchone()
                    next_before_id = id_result['max_id'] if id_result else None
                    next_before_date = max_date.isoformat()
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM articles WHERE published_on < %s) as has_more",
                        (max_date,)
                    )
                    more_result = cur.fetchone()
                    has_more = more_result['has_more'] if more_result else False
                else:
                    next_before_id = None
                    next_before_date = None
                    has_more = False

        response_data = {
            "articles": articles,
            "next_before_date": next_before_date,
            "next_before_id": next_before_id,
            "has_more": has_more
        }

        return _build_conditional_response(response_data)

    except Exception as e:
        logger.error(f"获取当天文章失败: {e}")
        return jsonify({"error": "获取当天文章失败"}), 500


@bp.route('/', methods=['GET'])
def get_articles():
    """获取文章列表（分页）。

    查询参数：
        v: 接口版本（可选，默认 1）
        before_id: 加载 ID 小于此值的文章（必填）
        before_date: 游标日期（v2 必填）
        limit: 返回数量（可选，默认 20）

    返回：
        {
            "articles": [...],
            "next_before_date": "2025-01-15",
            "next_before_id": 61,
            "has_more": true
        }
    """
    try:
        limit = min(int(request.args.get('limit', 20)), 100)  # 最多100篇
        version_str = request.args.get('v', '1')
        try:
            version = int(version_str)
        except ValueError:
            return jsonify({"error": "v 参数应为整数"}), 400

        if version not in (1, 2):
            return jsonify({"error": "不支持的 v 参数"}), 400

        before_id_str = request.args.get('before_id')

        # before_id 为必填参数
        if before_id_str is None:
            return jsonify({"error": "before_id 参数为必填，请使用 /today 端点获取首页数据"}), 400

        try:
            before_id = int(before_id_str)
        except ValueError:
            return jsonify({"error": "before_id 参数应为整数"}), 400

        before_date_str = request.args.get('before_date')
        if version == 2:
            if not before_date_str:
                return jsonify({"error": "before_date 参数为必填"}), 400
            try:
                before_date = date.fromisoformat(before_date_str)
            except ValueError:
                return jsonify({"error": "before_date 参数格式应为 YYYY-MM-DD"}), 400
        else:
            before_date = None

        if version == 2:
            sql = """
                SELECT id, title, unit, link, published_on, summary, attachments, created_at
                FROM articles
                WHERE (published_on < %s)
                   OR (published_on = %s AND id < %s)
                ORDER BY published_on DESC, id DESC
                LIMIT %s
            """
            params = (before_date, before_date, before_id, limit)
        else:
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
                "next_before_date": None,
                "next_before_id": None,
                "has_more": False
            }
        else:
            last_row = rows[-1]
            next_before_id = last_row['id']
            next_before_date = last_row['published_on'].isoformat() if last_row['published_on'] else None

            if version == 2:
                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT EXISTS(
                            SELECT 1 FROM articles
                            WHERE (published_on < %s)
                               OR (published_on = %s AND id < %s)
                        ) as has_more
                        """,
                        (last_row['published_on'], last_row['published_on'], next_before_id)
                    )
                    result = cur.fetchone()
                    has_more = result['has_more'] if result else False
            else:
                with db_session() as conn, conn.cursor() as cur:
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM articles WHERE id < %s) as has_more",
                        (next_before_id,)
                    )
                    result = cur.fetchone()
                    has_more = result['has_more'] if result else False

            response_data = {
                "articles": articles,
                "next_before_date": next_before_date,
                "next_before_id": next_before_id,
                "has_more": has_more
            }

        return _build_conditional_response(response_data)

    except Exception as e:
        logger.error(f"获取文章列表失败: {e}")
        return jsonify({"error": "获取文章列表失败"}), 500


@bp.route('/count', methods=['GET'])
def get_articles_count():
    """获取文章总数（不分页）。"""
    try:
        with db_session() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM articles")
            result = cur.fetchone()
        total = int(result['total']) if result and result.get('total') is not None else 0
        return jsonify({"total": total}), 200
    except Exception as e:
        logger.error(f"获取文章总数失败: {e}")
        return jsonify({"error": "获取文章总数失败"}), 500


@bp.route('/<int:article_id>', methods=['GET'])
def get_article_detail(article_id: int):
    """获取文章详情。

    根据文章ID获取完整的文章信息，包括内容和附件。
    支持 ETag 条件请求（304 Not Modified）。

    参数：
        article_id: 文章ID

    返回：
        包含文章详情的JSON响应
    """
    try:
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

        return _build_conditional_response(article_data)

    except Exception as e:
        logger.error(f"获取文章详情失败: {e}")
        return jsonify({"error": "获取文章详情失败"}), 500
