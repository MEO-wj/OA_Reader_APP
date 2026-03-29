# Crawler AI 主力/兜底模型策略 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 crawler 的 AI 轮询负载均衡替换为主力 + 兜底两级模型策略。

**Architecture:** 新增 `PrimaryFallbackBalancer` 替换现有 `AILoadBalancer`，`config.py` 用 6 个扁平环境变量配置主力/兜底模型，`summarizer.py` 改为"主力失败→兜底重试"流程。

**Tech Stack:** Python 3.11, pytest, dataclasses, requests

---

### Task 1: 重写 `ai_load_balancer.py`

**Files:**
- Modify: `crawler/services/ai_load_balancer.py` (全文重写)
- Test: `crawler/tests/test_ai_load_balancer.py` (新建)

**Step 1: 写失败测试 — PrimaryFallbackBalancer 基本行为**

创建 `crawler/tests/test_ai_load_balancer.py`:

```python
"""PrimaryFallbackBalancer 单元测试。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from crawler.services.ai_load_balancer import ModelConfig, PrimaryFallbackBalancer


def _make_config(prefix: str = "primary") -> ModelConfig:
    return ModelConfig(
        api_key=f"sk-{prefix}-key",
        base_url=f"https://api.{prefix}.com/v1/chat/completions",
        model=f"{prefix}-model",
    )


class TestPrimaryFallbackBalancer:
    """主力/兜底负载均衡器测试。"""

    def test_get_model_returns_primary(self):
        balancer = PrimaryFallbackBalancer(
            primary=_make_config("primary"),
            fallback=_make_config("fallback"),
        )
        model = balancer.get_model()
        assert model.model == "primary-model"

    def test_get_fallback_returns_fallback(self):
        balancer = PrimaryFallbackBalancer(
            primary=_make_config("primary"),
            fallback=_make_config("fallback"),
        )
        model = balancer.get_fallback()
        assert model.model == "fallback-model"

    def test_mark_429_sets_cooldown(self):
        config = _make_config()
        balancer = PrimaryFallbackBalancer(
            primary=config,
            fallback=_make_config("fallback"),
        )
        assert config.is_available
        balancer.mark_429(config, cooldown_seconds=60)
        assert not config.is_available

    def test_mark_429_cooldown_expires(self):
        config = _make_config()
        balancer = PrimaryFallbackBalancer(
            primary=config,
            fallback=_make_config("fallback"),
        )
        balancer.mark_429(config, cooldown_seconds=60)
        assert not config.is_available
        # 模拟时间流逝
        with patch("crawler.services.ai_load_balancer.time") as mock_time:
            mock_time.time.return_value = time.time() + 61
            assert config.is_available


class TestModelConfig:
    """ModelConfig 保留行为测试。"""

    def test_default_available(self):
        config = _make_config()
        assert config.is_available

    def test_mark_429_makes_unavailable(self):
        config = _make_config()
        config.mark_429(cooldown_seconds=30)
        assert not config.is_available

    def test_mask_key_short(self):
        from crawler.services.ai_load_balancer import _mask_key
        assert _mask_key("short") == "***"

    def test_mask_key_long(self):
        from crawler.services.ai_load_balancer import _mask_key
        result = _mask_key("sk-abcdefgh12345678end")
        assert result.startswith("sk-abcde")
        assert result.endswith("6end")
```

**Step 2: 运行测试确认失败**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/test_ai_load_balancer.py -v`
Expected: FAIL — `PrimaryFallbackBalancer` 不存在

**Step 3: 重写 `ai_load_balancer.py`**

```python
"""AI模型负载均衡器（爬虫端）。

主力/兜底两级模型策略：
- 优先使用主力模型（便宜/快速）
- 主力失败时切换到兜底模型（稳定/昂贵）
- 支持 429 错误自动冷却
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """单个模型配置。

    Attributes:
        api_key: API密钥
        base_url: API基础URL
        model: 模型名称
        _429_until: 该配置被429禁用到的截止时间（Unix时间戳）
    """

    api_key: str
    base_url: str
    model: str
    _429_until: float = 0.0

    @property
    def is_available(self) -> bool:
        """检查配置是否可用（未在429禁用期内）。"""
        return time.time() >= self._429_until

    def mark_429(self, cooldown_seconds: int = 60) -> None:
        """标记该配置为429状态，设置冷却时间。"""
        self._429_until = time.time() + cooldown_seconds
        masked_key = _mask_key(self.api_key)
        logger.warning(
            "[429] 模型: %s @ %s | key: %s | 冷却: %s秒",
            self.model,
            self.base_url,
            masked_key,
            cooldown_seconds,
        )


@dataclass
class PrimaryFallbackBalancer:
    """主力/兜底两级模型策略。

    优先使用主力模型，失败时切换到兜底模型。
    """

    primary: ModelConfig
    fallback: ModelConfig

    def get_model(self) -> ModelConfig:
        """返回主力模型配置。"""
        return self.primary

    def get_fallback(self) -> ModelConfig:
        """返回兜底模型配置。"""
        return self.fallback

    def mark_429(self, model: ModelConfig, cooldown_seconds: int = 60) -> None:
        """标记指定模型为429状态。"""
        model.mark_429(cooldown_seconds)


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "***"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"
```

**Step 4: 运行测试确认通过**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/test_ai_load_balancer.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add crawler/services/ai_load_balancer.py crawler/tests/test_ai_load_balancer.py
git commit -m "refactor(crawler): 用 PrimaryFallbackBalancer 替换轮询负载均衡器"
```

---

### Task 2: 更新 `config.py` 配置层

**Files:**
- Modify: `crawler/config.py`
- Test: `crawler/tests/test_config.py` (新建)

**Step 1: 写失败测试 — 新配置属性**

创建 `crawler/tests/test_config.py`:

```python
"""Config 配置层单元测试。"""

from __future__ import annotations

import os
import pytest

from crawler.config import Config


class TestAiProviderMode:
    """ai_provider_mode 推断逻辑测试。"""

    def test_single_mode_when_no_primary_env(self, tmp_path):
        """未配置 AI_PRIMARY_* 时为 single 模式。"""
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=sk-test\nAI_BASE_URL=http://test\nAI_MODEL=gpt-4\n")
        config = Config(env_file=env_file)
        assert config.ai_provider_mode == "single"

    def test_fallback_mode_when_primary_and_fallback_configured(self, tmp_path):
        """配置了 AI_PRIMARY_* + AI_FALLBACK_* 时为 fallback 模式。"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AI_PRIMARY_API_KEY=sk-primary\n"
            "AI_PRIMARY_BASE_URL=http://primary/v1/chat/completions\n"
            "AI_PRIMARY_MODEL=model-a\n"
            "AI_FALLBACK_API_KEY=sk-fallback\n"
            "AI_FALLBACK_BASE_URL=http://fallback/v1/chat/completions\n"
            "AI_FALLBACK_MODEL=model-b\n"
        )
        config = Config(env_file=env_file)
        assert config.ai_provider_mode == "fallback"
        assert config.ai_primary_api_key == "sk-primary"
        assert config.ai_primary_base_url == "http://primary/v1/chat/completions"
        assert config.ai_primary_model == "model-a"
        assert config.ai_fallback_api_key == "sk-fallback"
        assert config.ai_fallback_base_url == "http://fallback/v1/chat/completions"
        assert config.ai_fallback_model == "model-b"

    def test_env_override_takes_priority(self, tmp_path, monkeypatch):
        """环境变量覆盖 .env 文件的值。"""
        env_file = tmp_path / ".env"
        env_file.write_text("AI_PRIMARY_MODEL=old-model\n")
        monkeypatch.setenv("AI_PRIMARY_MODEL", "new-model")
        monkeypatch.setenv("AI_PRIMARY_API_KEY", "sk-key")
        monkeypatch.setenv("AI_PRIMARY_BASE_URL", "http://url")
        monkeypatch.setenv("AI_FALLBACK_API_KEY", "sk-fb")
        monkeypatch.setenv("AI_FALLBACK_BASE_URL", "http://fb-url")
        monkeypatch.setenv("AI_FALLBACK_MODEL", "fb-model")
        config = Config(env_file=env_file)
        assert config.ai_primary_model == "new-model"
        assert config.ai_provider_mode == "fallback"
```

**Step 2: 运行测试确认失败**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/test_config.py -v`
Expected: FAIL — `ai_provider_mode` 不存在

**Step 3: 修改 `config.py`**

在 `__init__` 的默认值区域：
- 删除 `self.ai_models` 和 `self.ai_enable_load_balancing`
- 新增：
  ```python
  self.ai_primary_api_key: Optional[str] = None
  self.ai_primary_base_url: Optional[str] = None
  self.ai_primary_model: Optional[str] = None
  self.ai_fallback_api_key: Optional[str] = None
  self.ai_fallback_base_url: Optional[str] = None
  self.ai_fallback_model: Optional[str] = None
  self.ai_provider_mode: str = "single"  # "single" | "fallback"
  ```

在 `_override_with_environment` 的 `keys` 列表中：
- 删除 `"AI_MODELS"` 和 `"AI_ENABLE_LOAD_BALANCING"`
- 新增 `"AI_PRIMARY_API_KEY"`, `"AI_PRIMARY_BASE_URL"`, `"AI_PRIMARY_MODEL"`, `"AI_FALLBACK_API_KEY"`, `"AI_FALLBACK_BASE_URL"`, `"AI_FALLBACK_MODEL"`

在 `_apply_setting` 中：
- 删除 `AI_MODELS` 和 `AI_ENABLE_LOAD_BALANCING` 分支
- 新增 6 个新键的分支
- 在 `load()` 末尾添加 `_detect_provider_mode()` 调用

新增方法：
```python
def _detect_provider_mode(self) -> None:
    """根据已加载的配置推断 ai_provider_mode。"""
    has_primary = all([
        self.ai_primary_api_key,
        self.ai_primary_base_url,
        self.ai_primary_model,
    ])
    has_fallback = all([
        self.ai_fallback_api_key,
        self.ai_fallback_base_url,
        self.ai_fallback_model,
    ])
    if has_primary and has_fallback:
        self.ai_provider_mode = "fallback"
    else:
        self.ai_provider_mode = "single"
```

**Step 4: 运行测试确认通过**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/test_config.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add crawler/config.py crawler/tests/test_config.py
git commit -m "refactor(crawler): 用主力/兜底扁平环境变量替换 AI_MODELS JSON 配置"
```

---

### Task 3: 更新 `summarizer.py` 调用逻辑

**Files:**
- Modify: `crawler/summarizer.py`
- Test: `crawler/tests/test_summarizer.py` (新建)

**Step 1: 写失败测试 — 主力成功直接返回**

创建 `crawler/tests/test_summarizer.py`:

```python
"""Summarizer 主力/兜底策略单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from crawler.summarizer import Summarizer


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {
        "choices": [{"message": {"content": "这是摘要"}}]
    }
    return resp


class TestSummarizerFallback:
    """主力/兜底切换逻辑测试。"""

    def test_primary_success_returns_immediately(self):
        """主力模型成功时直接返回，不调用兜底。"""
        config = MagicMock()
        config.ai_provider_mode = "fallback"
        config.ai_primary_api_key = "sk-primary"
        config.ai_primary_base_url = "http://primary/v1/chat/completions"
        config.ai_primary_model = "primary-model"
        config.ai_fallback_api_key = "sk-fallback"
        config.ai_fallback_base_url = "http://fallback/v1/chat/completions"
        config.ai_fallback_model = "fallback-model"

        with patch("crawler.summarizer.http_post") as mock_post, \
             patch("crawler.summarizer._get_load_balancer") as mock_lb:
            # 不走 balancer 路径，直接测 summarize 内部逻辑
            pass

        # 用更直接的方式：mock balancer
        from crawler.services.ai_load_balancer import PrimaryFallbackBalancer, ModelConfig

        primary = ModelConfig("sk-p", "http://p/v1/chat/completions", "p-model")
        fallback = ModelConfig("sk-f", "http://f/v1/chat/completions", "f-model")
        balancer = PrimaryFallbackBalancer(primary=primary, fallback=fallback)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", return_value=_mock_response()) as mock_post:
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_count == 1
        # 验证用的是主力模型
        call_args = mock_post.call_args
        assert call_args[0][0] == "http://p/v1/chat/completions"

    def test_primary_fails_uses_fallback(self):
        """主力模型失败时切换到兜底模型。"""
        from crawler.services.ai_load_balancer import PrimaryFallbackBalancer, ModelConfig

        primary = ModelConfig("sk-p", "http://p/v1/chat/completions", "p-model")
        fallback = ModelConfig("sk-f", "http://f/v1/chat/completions", "f-model")
        balancer = PrimaryFallbackBalancer(primary=primary, fallback=fallback)

        fail_resp = _mock_response(status_code=500, json_data={"error": "internal"})
        success_resp = _mock_response(status_code=200)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", side_effect=[fail_resp, success_resp]) as mock_post:
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_count == 2
        # 第二次调用应该用兜底 URL
        second_call_url = mock_post.call_args_list[1][0][0]
        assert second_call_url == "http://f/v1/chat/completions"

    def test_both_fail_returns_none(self):
        """主力 + 兜底都失败时返回 None。"""
        from crawler.services.ai_load_balancer import PrimaryFallbackBalancer, ModelConfig

        primary = ModelConfig("sk-p", "http://p/v1/chat/completions", "p-model")
        fallback = ModelConfig("sk-f", "http://f/v1/chat/completions", "f-model")
        balancer = PrimaryFallbackBalancer(primary=primary, fallback=fallback)

        fail_resp = _mock_response(status_code=500, json_data={"error": "internal"})

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", return_value=fail_resp):
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result is None

    def test_primary_429_triggers_fallback(self):
        """主力模型 429 时标记冷却并切换到兜底。"""
        from crawler.services.ai_load_balancer import PrimaryFallbackBalancer, ModelConfig

        primary = ModelConfig("sk-p", "http://p/v1/chat/completions", "p-model")
        fallback = ModelConfig("sk-f", "http://f/v1/chat/completions", "f-model")
        balancer = PrimaryFallbackBalancer(primary=primary, fallback=fallback)

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.json.return_value = {}
        success_resp = _mock_response(status_code=200)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", side_effect=[resp_429, success_resp]):
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert not primary.is_available  # 被标记了 429 冷却

    def test_no_balancer_uses_single_config(self):
        """无 balancer 时走单模型配置（向后兼容）。"""
        config = MagicMock()
        config.ai_provider_mode = "single"
        config.api_key = "sk-single"
        config.ai_base_url = "http://single/v1/chat/completions"
        config.ai_model = "single-model"

        with patch("crawler.summarizer._get_load_balancer", return_value=None), \
             patch("crawler.summarizer.http_post", return_value=_mock_response()) as mock_post:
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = config
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        call_url = mock_post.call_args[0][0]
        assert call_url == "http://single/v1/chat/completions"

    def test_primary_network_error_uses_fallback(self):
        """主力网络错误（http_post 返回 None）时切兜底。"""
        from crawler.services.ai_load_balancer import PrimaryFallbackBalancer, ModelConfig

        primary = ModelConfig("sk-p", "http://p/v1/chat/completions", "p-model")
        fallback = ModelConfig("sk-f", "http://f/v1/chat/completions", "f-model")
        balancer = PrimaryFallbackBalancer(primary=primary, fallback=fallback)

        success_resp = _mock_response(status_code=200)

        with patch("crawler.summarizer._get_load_balancer", return_value=balancer), \
             patch("crawler.summarizer.http_post", side_effect=[None, success_resp]) as mock_post:
            summarizer = Summarizer.__new__(Summarizer)
            summarizer.config = MagicMock()
            result = summarizer.summarize("测试内容")

        assert result == "这是摘要"
        assert mock_post.call_count == 2
```

**Step 2: 运行测试确认失败**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/test_summarizer.py -v`
Expected: FAIL — `summarize()` 方法尚未支持 fallback 逻辑

**Step 3: 重写 `summarizer.py`**

```python
"""OA 系统文章 AI 摘要生成模块。

该模块负责使用 AI 模型（OpenAI Chat 兼容）为爬取到的 OA 系统文章生成摘要。
支持主力/兜底两级模型策略：主力失败自动切换兜底模型重试。
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from crawler.config import Config
from crawler.services.ai_load_balancer import ModelConfig, PrimaryFallbackBalancer
from crawler.utils import http_post

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    """角色设定：
你是一个专业的事件通知摘要生成器，擅长从各类通知公告中提取核心信息，并生成客观、中立的简短摘要。

目标任务：
请根据用户输入的通知事件消息（如公示、公告、通知等），提取关键要素，生成一段简洁的摘要。摘要需完全基于文本事实，不添加任何主观评价或额外信息。

具体要求：
1. **提取关键要素**：
   - **事件主题**：通知的核心事项（如"国家奖学金候选人公示"）。
   - **发起单位**：发布通知的机构或部门（如"商学院"）。
   - **主要行动**：通知中的核心决定或步骤（如"推荐候选人""公示结果"）。
   - **关键细节**：包括具体名单、时间节点（如公示截止日期）、地点、联系方式等。
   - **目的或要求**：如"征询意见"或"反馈方式"。

2. **摘要格式**：
   - 语言简洁、正式，尽量一句话直接陈述事实。
   - 避免使用修饰性词语（如"重要""隆重"）和主观表述（如"值得祝贺"）。

3. **约束条件**：
   - 仅总结通知中明确提及的内容，不推断未说明的信息。
   - 忽略通知中的格式性文字（如"特此通知""附件下载"）。
   - 直接返回摘要文本，不输出任何其他信息。

请基于以下通知生成摘要："""
)

_load_balancer: PrimaryFallbackBalancer | None = None
_load_balancer_initialized = False


def _get_load_balancer(config: Config) -> PrimaryFallbackBalancer | None:
    """获取或创建负载均衡器单例。"""
    global _load_balancer, _load_balancer_initialized
    if _load_balancer_initialized:
        return _load_balancer

    if config.ai_provider_mode == "fallback":
        _load_balancer = PrimaryFallbackBalancer(
            primary=ModelConfig(
                api_key=config.ai_primary_api_key,
                base_url=config.ai_primary_base_url,
                model=config.ai_primary_model,
            ),
            fallback=ModelConfig(
                api_key=config.ai_fallback_api_key,
                base_url=config.ai_fallback_base_url,
                model=config.ai_fallback_model,
            ),
        )
        logger.info("爬虫AI主力/兜底策略已启用")
    else:
        logger.debug("爬虫AI单模型模式")

    _load_balancer_initialized = True
    return _load_balancer


def _is_429_response(resp: requests.Response) -> bool:
    """判断是否为429速率限制响应。"""
    if resp.status_code == 429:
        return True
    try:
        data = resp.json()
        error = data.get("error", {})
        if isinstance(error, dict):
            return "429" in str(error.get("code", "")).lower()
    except (ValueError, TypeError):
        return False
    return False


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "***"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"


def _call_ai(model_config: ModelConfig, content: str) -> requests.Response | None:
    """调用 AI API 发送摘要请求。

    Args:
        model_config: 模型配置
        content: 待摘要的文章内容

    Returns:
        HTTP 响应对象，网络错误时返回 None
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model_config.api_key}",
    }
    payload = {
        "model": model_config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    masked_key = _mask_key(model_config.api_key)
    logger.info("使用模型: %s @ %s (key: %s)", model_config.model, model_config.base_url, masked_key)

    return http_post(model_config.base_url, payload=payload, headers=headers, timeout=60)


def _extract_summary(resp: requests.Response) -> str | None:
    """从 AI API 响应中提取摘要文本。

    Args:
        resp: HTTP 响应对象

    Returns:
        摘要文本，提取失败时返回 None
    """
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    text = choices[-1]["message"].get("content", "").strip()
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    text = text.lstrip("# ").lstrip()
    return text


class Summarizer:
    """AI 摘要生成器类。

    支持主力/兜底两级模型策略：
    1. 优先使用主力模型
    2. 任何失败（429、超时、500、空响应）触发兜底重试
    3. 兜底也失败则返回 None（由 pipeline 重试逻辑处理）
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()

    def summarize(self, content: str) -> str | None:
        """为给定的文章内容生成 AI 摘要。

        Args:
            content: 待摘要的文章内容

        Returns:
            摘要文本，失败时返回 None
        """
        balancer = _get_load_balancer(self.config)

        if balancer:
            return self._summarize_with_fallback(balancer, content)

        # 单模型模式（向后兼容）
        return self._summarize_single(content)

    def _summarize_with_fallback(self, balancer: PrimaryFallbackBalancer, content: str) -> str | None:
        """主力/兜底两级模型策略。"""
        # 尝试主力模型
        primary = balancer.get_model()
        result = self._try_model(primary, content)
        if result is not None:
            return result

        logger.warning("主力模型失败，切换到兜底模型")

        # 主力失败，尝试兜底模型
        fallback = balancer.get_fallback()
        return self._try_model(fallback, content)

    def _try_model(self, model_config: ModelConfig, content: str) -> str | None:
        """尝试用指定模型生成摘要。"""
        resp = _call_ai(model_config, content)
        if resp is None:
            logger.warning("模型 %s 请求异常", model_config.model)
            return None

        if resp.status_code != 200:
            if _is_429_response(resp):
                balancer = _get_load_balancer(self.config)
                if balancer:
                    balancer.mark_429(model_config)
            logger.warning("模型 %s 返回错误: %s", model_config.model, resp.status_code)
            return None

        summary = _extract_summary(resp)
        if not summary:
            logger.warning("模型 %s 返回空内容", model_config.model)
            return None
        return summary

    def _summarize_single(self, content: str) -> str | None:
        """单模型模式（向后兼容）。"""
        if not (self.config.api_key and self.config.ai_base_url and self.config.ai_model):
            return "[AI 未配置]"

        model_config = ModelConfig(
            api_key=self.config.api_key,
            base_url=self.config.ai_base_url,
            model=self.config.ai_model,
        )
        resp = _call_ai(model_config, content)
        if resp is None or resp.status_code != 200:
            return None

        return _extract_summary(resp)
```

**Step 4: 运行测试确认通过**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/test_summarizer.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add crawler/summarizer.py crawler/tests/test_summarizer.py
git commit -m "feat(crawler): summarizer 主力/兜底两级模型策略"
```

---

### Task 4: 更新 `.env` 配置文件

**Files:**
- Modify: `crawler/.env`

**Step 1: 替换 AI 配置段**

将 `.env` 中的 AI 配置段从：

```
API_KEY=sk-fXUgp24gPvf6XS4aCswRAo9sDAjw3NE2kWLKZGT7XpAq3jVq
AI_BASE_URL=http://186.1.1.2:4417/v1/completions
AI_MODEL=glm-4.6v-flash

AI_MODELS=[{"api_key": "sk-fXUgp24gPvf6XS4aCswRAo9sDAjw3NE2kWLKZGT7XpAq3jVq","base_url": "http://186.1.1.2:4417/v1/chat/completions","models": ["minimax-m2.5"]}]
AI_ENABLE_LOAD_BALANCING=true
```

改为（用户需填入实际兜底配置）：

```
# 单模型配置（向后兼容，fallback 模式下不使用）
API_KEY=sk-fXUgp24gPvf6XS4aCswRAo9sDAjw3NE2kWLKZGT7XpAq3jVq
AI_BASE_URL=http://186.1.1.2:4417/v1/completions
AI_MODEL=glm-4.6v-flash

# 主力模型
AI_PRIMARY_API_KEY=sk-fXUgp24gPvf6XS4aCswRAo9sDAjw3NE2kWLKZGT7XpAq3jVq
AI_PRIMARY_BASE_URL=http://186.1.1.2:4417/v1/chat/completions
AI_PRIMARY_MODEL=minimax-m2.5

# 兜底模型
AI_FALLBACK_API_KEY=your-fallback-key
AI_FALLBACK_BASE_URL=https://api.openai.com/v1/chat/completions
AI_FALLBACK_MODEL=gpt-4o-mini
```

**Step 2: 运行全量测试确认无回归**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/ -v`
Expected: 全部 passed（跳过需要数据库的集成测试）

**Step 3: Commit**

```bash
git add crawler/.env
git commit -m "chore(crawler): 更新 .env 为主力/兜底模型配置"
```

---

### Task 5: 清理旧代码引用

**Files:**
- Verify: `crawler/pipeline.py`（确认无需改动）
- Verify: `crawler/embeddings.py`（确认无旧 balancer 引用）

**Step 1: 检查 pipeline.py 无需改动**

`pipeline.py` 通过 `Summarizer` 类间接使用负载均衡器，不直接引用 `AILoadBalancer`。确认无 `ai_load_balancer` 或 `AILoadBalancer` 的 import。

**Step 2: 全局搜索旧引用**

Run: `grep -rn "AILoadBalancer\|ai_enable_load_balancing\|ai_models\|AI_MODELS\|AI_ENABLE_LOAD_BALANCING" crawler/ --include="*.py" --exclude-dir=.venv`
Expected: 0 matches（所有旧引用已清除）

**Step 3: 最终全量测试**

Run: `cd /home/handy/OAP && uv run --directory crawler pytest crawler/tests/ -v`
Expected: 全部 passed

**Step 4: Commit**

```bash
git commit --allow-empty -m "chore(crawler): 确认旧负载均衡引用已清理完毕"
```
