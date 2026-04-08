"""爬虫通用工具函数。"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from typing import Any

import requests

DATE_FMT = "%Y-%m-%d"
DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def parse_date(s: str) -> datetime:
    """按统一格式解析日期字符串。"""
    return datetime.strptime(s, DATE_FMT)


def format_date(d: datetime) -> str:
    """按统一格式输出日期字符串。"""
    return d.strftime(DATE_FMT)


def random_delay(min_sec: float, max_sec: float, enabled: bool = True, msg: str = "延迟") -> None:
    """执行随机延迟。"""
    if not enabled:
        return
    delay = random.uniform(min_sec, max_sec)
    print(f"⏳ {msg} {delay:.1f} 秒...")
    time.sleep(delay)


def safe_json_parse(s: str, default: Any = None) -> Any:
    """安全解析 JSON 字符串。"""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


def http_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 60,
) -> requests.Response | None:
    """统一的 HTTP POST 封装。"""
    try:
        return requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        print(f"请求失败: {exc}")
        return None
