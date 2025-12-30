from __future__ import annotations

import logging

import redis
import json

from datetime import datetime, date, timedelta

from crawler.config import Config


DEFAULT_CACHE_DAYS = 3


def _serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    return value


def _serialize_row(row: dict) -> dict:
    return {key: _serialize_value(val) for key, val in row.items()}


def _build_redis_client(cfg: Config) -> redis.Redis:
    return redis.Redis(
        host=cfg.redis_host,
        port=cfg.redis_port,
        db=cfg.redis_db,
        password=cfg.redis_password,
        socket_timeout=3,
        decode_responses=True,
    )


def refresh_today_cache(
    articles: list[dict],
    target_date: str,
    logger: logging.Logger | None = None,
) -> int:
    """刷新当天文章缓存（首页专用）。

    缓存键: articles:today
    TTL: 86400 秒（24 小时）- crawler 覆盖写入会重置 TTL

    Args:
        articles: 文章列表（当天所有文章）
        target_date: 目标日期（用于日志）
        logger: 日志记录器

    Returns:
        成功写入返回 1，失败返回 0
    """
    cfg = Config()
    log = logger or logging.getLogger(__name__)

    if not cfg.redis_host:
        return 0

    client = _build_redis_client(cfg)

    # 写入 articles:today（包含完整响应结构，所有文章）
    serialized = [_serialize_row(item) for item in articles]

    # 计算 next_before_id 和 has_more
    next_before_id = None
    next_before_date = None
    has_more = True

    if serialized:
        # 最后一个元素的 id 作为 next_before_id
        next_before_id = serialized[-1].get("id")
        next_before_date = target_date

    payload = {
        "articles": [{k: v for k, v in item.items() if k != "content"} for item in serialized],
        "next_before_date": next_before_date,
        "next_before_id": next_before_id,
        "has_more": has_more,  # crawler 无法判断是否有更早文章，由 backend 查询时确定
    }

    try:
        client.setex("articles:today", 86400, json.dumps(payload, ensure_ascii=False))
        log.info(
            "刷新 today 缓存成功",
            extra={"date": target_date, "count": len(articles), "next_before_id": next_before_id},
        )
        return 1
    except Exception as exc:
        log.warning(
            "刷新 today 缓存失败: %s" % exc,
            extra={"date": target_date},
        )
        return 0


def refresh_article_detail_cache(
    articles: list[dict],
    target_date: str,
    logger: logging.Logger | None = None,
    days: int = DEFAULT_CACHE_DAYS,
) -> int:
    """刷新文章详情缓存。

    为每篇文章生成 articles:detail:{id} 缓存。

    Args:
        articles: 文章列表
        target_date: 目标日期（用于日志）
        logger: 日志记录器
        days: 缓存天数（默认 3 天）

    Returns:
        成功写入的缓存数量
    """
    cfg = Config()
    log = logger or logging.getLogger(__name__)

    if not cfg.redis_host:
        return 0

    client = _build_redis_client(cfg)
    ttl_seconds = max(days, 1) * 86400

    serialized = [_serialize_row(item) for item in articles]
    updated = 0

    try:
        pipe = client.pipeline()
        for article in serialized:
            article_id = article.get("id")
            if article_id is None:
                continue
            detail_key = f"articles:detail:{article_id}"
            pipe.setex(
                detail_key,
                ttl_seconds,
                json.dumps(article, ensure_ascii=False),
            )
        results = pipe.execute()
        updated = sum(1 for result in results if result)
        log.info(
            "刷新 article detail 缓存成功",
            extra={"date": target_date, "updated": updated},
        )
    except Exception as exc:
        log.warning(
            "刷新 article detail 缓存失败: %s" % exc,
            extra={"date": target_date, "error": str(exc)},
        )
    return updated


def clear_article_list_cache(target_date: str, logger: logging.Logger | None = None) -> int:
    """清除指定日期的文章列表缓存（旧版兼容，实际清除 articles:list:*）。

    Args:
        target_date: 目标日期
        logger: 日志记录器

    Returns:
        删除的缓存键数量
    """
    cfg = Config()
    log = logger or logging.getLogger(__name__)

    if not cfg.redis_host:
        return 0

    client = _build_redis_client(cfg)

    pattern = f"articles:list:{target_date}:*"
    deleted = 0
    try:
        keys = list(client.scan_iter(match=pattern))
        if keys:
            deleted = client.delete(*keys)
            log.info("redis cache cleared", extra={"pattern": pattern, "deleted": deleted})
        deleted += clear_outdated_list_cache(client, days=DEFAULT_CACHE_DAYS, logger=log)
    except Exception as exc:
        log.warning("redis cache clear failed", extra={"pattern": pattern, "error": str(exc)})
    return deleted


def clear_outdated_list_cache(
    client: redis.Redis,
    days: int,
    logger: logging.Logger | None = None,
) -> int:
    """清除过期的文章列表缓存（旧版兼容）。

    Args:
        client: Redis 客户端
        days: 保留天数
        logger: 日志记录器

    Returns:
        删除的缓存键数量
    """
    log = logger or logging.getLogger(__name__)
    if days <= 0:
        return 0

    cutoff = datetime.now().date() - timedelta(days=days - 1)
    deleted = 0
    try:
        for key in client.scan_iter(match="articles:list:*"):
            parts = key.split(":")
            if len(parts) < 3:
                continue
            date_str = parts[2]
            try:
                date_value = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if date_value < cutoff:
                if client.delete(key):
                    deleted += 1
        if deleted:
            log.info(
                "redis cache cleanup complete",
                extra={"deleted": deleted, "cutoff": cutoff.isoformat()},
            )
    except Exception as exc:
        log.warning("redis cache cleanup failed", extra={"error": str(exc)})
    return deleted
