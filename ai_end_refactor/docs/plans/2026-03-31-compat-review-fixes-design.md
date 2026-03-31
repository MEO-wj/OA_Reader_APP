# 兼容端点审查修复设计

日期: 2026-03-31

## 背景

代码审查发现 5 个确认有效的问题需要修复。这些问题来自 AI End 旧接口兼容层的首次实现。

## 待修复问题

| # | 严重度 | 问题 | 文件 |
|---|--------|------|------|
| C1 | Important | 兼容端点无异常处理，下游错误暴露为裸 500 | main.py |
| I1 | Minor | top_k bool 类型未在模型层拒绝 | compat_models.py |
| I5 | Minor | 集成测试缺少成功路径 | test_compat_endpoints.py |
| M2 | Minor | tool_result 解析失败无日志 | compat_service.py |
| M3 | Minor | _today_range 中 Any 类型不精确 | compat_service.py |

## 方案：最小侵入式修复

### C1: 兼容端点异常处理

在 `main.py` 的 `ask_compat`、`clear_memory_compat`、`embed_compat` 三个函数体内添加 `try-except`，将 `Exception` 转为 `{"error": str(exc)}` 和 HTTP 500 响应。

```python
# 模式（三个端点统一）:
try:
    service = CompatService()
    payload = await service.ask(...)
    return JSONResponse(content=payload, media_type="application/json")
except Exception as exc:
    logger.exception("Compat endpoint error")
    return JSONResponse(status_code=500, content={"error": str(exc)})
```

选择逐端点添加而非全局异常处理器，因为：
- 影响范围精确控制在变更文件内
- 不改变项目其他端点的错误响应格式
- 与项目现有风格一致

### I1: top_k 模型层验证

在 `compat_models.py` 的 `AskCompatRequest` 上添加 `@field_validator('top_k')` 拒绝 `bool` 类型：

```python
from pydantic import BaseModel, field_validator

class AskCompatRequest(BaseModel):
    question: str | None = None
    top_k: int | str | None = None
    display_name: str | None = None
    user_id: str | None = None

    @field_validator('top_k', mode='before')
    @classmethod
    def reject_bool(cls, v):
        if isinstance(v, bool):
            raise ValueError('top_k must be an integer or string, not boolean')
        return v
```

注意：`mode='before'` 确保在 Pydantic 类型转换之前执行，拦截 `True`→`1` 的隐式强转。

### I5: 补充集成测试

在 `test_compat_endpoints.py` 中添加两个测试：

1. `test_clear_memory_success` — mock `CompatService.clear_memory`，验证返回 200 和 `{"cleared": true, "conversation_id": "..."}`。
2. `test_ask_with_user_id_success` — mock `CompatService.ask` 返回带 `conversation_id` 的结果，验证 200 和响应结构。

### M2: tool_result 解析失败日志

在 `compat_service.py:175` 的 `except (json.JSONDecodeError, TypeError)` 块中添加：

```python
except (json.JSONDecodeError, TypeError):
    logger.warning("Failed to parse tool_result as JSON: %s", raw_result[:200])
    parsed = None
```

截取前 200 字符避免日志过大。

### M3: 类型标注修正

将 `compat_service.py:38` 的 `tz: Any` 改为 `tz: ZoneInfo | timezone`。

## 不做的事

- 不引入全局异常处理器（影响范围超出兼容端点）
- 不修改 `Config.load()` 的调用模式（项目级既有问题）
- 不修改 `uuid4().hex[:8]` 的 ID 生成策略（项目级既有模式）
- 不添加 Pydantic Field 描述（项目风格一致性问题）
