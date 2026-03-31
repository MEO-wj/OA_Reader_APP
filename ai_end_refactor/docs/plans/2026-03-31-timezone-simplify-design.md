# 时区统一为 UTC+0 naive datetime

日期: 2026-03-31

## 背景

`_today_range()` 原设计支持 IANA 时区解析（如 `Asia/Shanghai`），但数据库 `created_at` 列是 `TIMESTAMP WITHOUT TIME ZONE`，asyncpg 拒绝 aware datetime 参数。之前的修复用 `.replace(tzinfo=None)` 兜底，但这保留了一个不必要的复杂层：时区解析 → UTC 转换 → 去 tzinfo。

既然数据库和服务器都以 UTC+0 工作，直接用 naive UTC datetime 计算即可，删除所有时区配置代码。

## 变更清单

### 1. `compat_service.py` — `_today_range()` 简化

删除 `tz_name` 参数，直接用 `datetime.utcnow()` 计算：

```python
def _today_range() -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end
```

删除 `from zoneinfo import ZoneInfo` 和 `from datetime import timezone`。

### 2. `compat_service.py` — `_resolve_session()` 简化

`_today_range(self.config.ai_compat_timezone)` → `_today_range()`

### 3. `settings.py` — 删除时区配置

删除：
- `ai_compat_timezone` 字段定义
- `with_defaults()` 中的 `ai_compat_timezone=None`
- `load()` 中的 `AI_COMPAT_TZ`/`AI_COMPAT_TIMEZONE` 环境变量读取
- `Config()` 构造参数中的 `ai_compat_timezone`

### 4. 删除 `test_config_compat.py`

整个文件删除。

### 5. `test_memory_compat.py` — mock 数据改 naive

`datetime(..., tzinfo=timezone.utc)` → `datetime(...)`，删除 `from datetime import timezone`。

### 6. `test_compat_service.py` — 简化

- 删除 `TestTodayRange.test_today_range_with_explicit_timezone`
- 简化 `TestTodayRange` 其余测试（无参数调用 `_today_range()`）
- `_make_config()` 删除 `ai_compat_timezone` 参数
- 删除 `from zoneinfo import ZoneInfo`、`from datetime import timezone`
