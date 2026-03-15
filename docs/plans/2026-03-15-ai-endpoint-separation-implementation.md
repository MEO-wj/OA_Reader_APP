# AI 服务抽离实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 backend 中的 AI 相关逻辑抽离成独立的 ai_end 服务，实现业务逻辑与 AI 能力的解耦。

**Architecture:**
- ai_end 作为独立 Flask 服务，提供 /ask API
- backend 通过 HTTP 调用 ai_end API
- 共享 PostgreSQL (pgvector) 数据库

**Tech Stack:** Flask, LangChain, LangGraph, Redis, Docker

---

## Task 1: 创建 ai_end 目录结构和基础文件

**Files:**
- Create: `ai_end/app.py`
- Create: `ai_end/config.py`
- Create: `ai_end/Dockerfile`
- Create: `ai_end/requirements.txt`
- Create: `ai_end/.env.example`
- Create: `ai_end/__init__.py`

**Step 1: 创建 ai_end 目录**

```bash
mkdir -p ai_end/services
touch ai_end/__init__.py
touch ai_end/services/__init__.py
```

**Step 2: 创建 ai_end/config.py**

创建文件 `ai_end/config.py`，包含 AI 相关配置：

```python
"""AI 服务配置加载器。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


class Config:
    """AI 服务配置。"""

    def __init__(self, env_file: str | Path | None = None) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        default_env = Path(__file__).resolve().parent / ".env"
        self.env_file = self._resolve_path(env_file) if env_file else default_env

        # 数据库配置
        self.database_url: Optional[str] = None

        # Redis 配置
        self.redis_host: str = "localhost"
        self.redis_port: int = 6379
        self.redis_db: int = 0
        self.redis_password: Optional[str] = None

        # Embedding 配置
        self.embed_base_url: Optional[str] = None
        self.embed_model: Optional[str] = None
        self.embed_api_key: Optional[str] = None
        self.embed_dim: int = 1024

        # AI 配置
        self.ai_base_url: Optional[str] = None
        self.ai_model: Optional[str] = None
        self.api_key: Optional[str] = None
        self.ai_vector_limit_days: Optional[int] = None
        self.ai_vector_limit_count: Optional[int] = None
        self.ai_recency_half_life_days: float = 180.0
        self.ai_recency_weight: float = 0.2

        # AI负载均衡配置
        self.ai_models: list[dict] = []
        self.ai_enable_load_balancing: bool = True

        # AI请求队列配置
        self.ai_queue_enabled: bool = True
        self.ai_queue_max_size: int = 20
        self.ai_queue_timeout: int = 30

        # Flask 配置
        self.flask_host: str = "0.0.0.0"
        self.flask_port: int = 4421

        self.load()

    def load(self) -> None:
        self._load_from_env_file()
        self._override_with_environment()

    def _resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _load_from_env_file(self) -> None:
        if not self.env_file.exists():
            return
        try:
            for raw in self.env_file.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, raw_value = line.split("=", 1)
                self._apply_setting(key.strip().upper(), raw_value.strip())
        except OSError as exc:
            raise RuntimeError(f"无法读取配置文件: {self.env_file}") from exc

    def _override_with_environment(self) -> None:
        keys = [
            "DATABASE_URL",
            "REDIS_HOST",
            "REDIS_PORT",
            "REDIS_DB",
            "REDIS_PASSWORD",
            "EMBED_BASE_URL",
            "EMBED_MODEL",
            "EMBED_API_KEY",
            "EMBED_DIM",
            "AI_BASE_URL",
            "AI_MODEL",
            "API_KEY",
            "AI_VECTOR_LIMIT_DAYS",
            "AI_VECTOR_LIMIT_COUNT",
            "AI_RECENCY_HALF_LIFE_DAYS",
            "AI_RECENCY_WEIGHT",
            "AI_MODELS",
            "AI_ENABLE_LOAD_BALANCING",
            "AI_QUEUE_ENABLED",
            "AI_QUEUE_MAX_SIZE",
            "AI_QUEUE_TIMEOUT",
            "FLASK_HOST",
            "FLASK_PORT",
        ]
        for key in keys:
            value = os.getenv(key)
            if value is not None and value != "":
                self._apply_setting(key, value)

    def _apply_setting(self, key: str, raw_value: str) -> None:
        value = raw_value.strip()
        if key == "DATABASE_URL":
            self.database_url = value or None
        elif key == "REDIS_HOST":
            self.redis_host = value
        elif key == "REDIS_PORT":
            try:
                self.redis_port = int(value)
            except ValueError:
                pass
        elif key == "REDIS_DB":
            try:
                self.redis_db = int(value)
            except ValueError:
                pass
        elif key == "REDIS_PASSWORD":
            self.redis_password = value or None
        elif key == "EMBED_BASE_URL":
            self.embed_base_url = value or None
        elif key == "EMBED_MODEL":
            self.embed_model = value or None
        elif key == "EMBED_API_KEY":
            self.embed_api_key = value or None
        elif key == "EMBED_DIM":
            try:
                self.embed_dim = int(value)
            except ValueError:
                pass
        elif key == "AI_BASE_URL":
            self.ai_base_url = value or None
        elif key == "AI_MODEL":
            self.ai_model = value or None
        elif key == "API_KEY":
            self.api_key = value or None
        elif key == "AI_VECTOR_LIMIT_DAYS":
            try:
                self.ai_vector_limit_days = int(value)
            except ValueError:
                pass
        elif key == "AI_VECTOR_LIMIT_COUNT":
            try:
                self.ai_vector_limit_count = int(value)
            except ValueError:
                pass
        elif key == "AI_RECENCY_HALF_LIFE_DAYS":
            try:
                self.ai_recency_half_life_days = float(value)
            except ValueError:
                pass
        elif key == "AI_RECENCY_WEIGHT":
            try:
                self.ai_recency_weight = float(value)
            except ValueError:
                pass
        elif key == "AI_MODELS":
            try:
                self.ai_models = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif key == "AI_ENABLE_LOAD_BALANCING":
            self.ai_enable_load_balancing = value.lower() in ("1", "true", "yes", "on")
        elif key == "AI_QUEUE_ENABLED":
            self.ai_queue_enabled = value.lower() in ("1", "true", "yes", "on")
        elif key == "AI_QUEUE_MAX_SIZE":
            try:
                self.ai_queue_max_size = int(value)
            except ValueError:
                pass
        elif key == "AI_QUEUE_TIMEOUT":
            try:
                self.ai_queue_timeout = int(value)
            except ValueError:
                pass
        elif key == "FLASK_HOST":
            self.flask_host = value
        elif key == "FLASK_PORT":
            try:
                self.flask_port = int(value)
            except ValueError:
                pass


__all__ = ["Config"]
```

**Step 3: 创建 requirements.txt**

创建文件 `ai_end/requirements.txt`:

```text
flask==3.0.0
flask-cors==4.0.0
redis==5.0.1
psycopg2-binary==2.9.9
requests==2.31.0
langchain-openai==0.1.8
langgraph==0.2.27
python-dotenv==1.0.0
gunicorn==21.2.0
```

**Step 4: 创建 .env.example**

创建文件 `ai_end/.env.example`:

```env
# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/oap

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Embedding 服务
EMBED_BASE_URL=https://api.example.com/v1/embeddings
EMBED_MODEL=text-embedding-3-large
EMBED_API_KEY=sk-xxx
EMBED_DIM=1024

# AI 服务
AI_BASE_URL=https://api.example.com/v1
AI_MODEL=glm-4-flash
API_KEY=sk-xxx
AI_VECTOR_LIMIT_DAYS=365
AI_VECTOR_LIMIT_COUNT=10000
AI_RECENCY_HALF_LIFE_DAYS=180
AI_RECENCY_WEIGHT=0.2

# AI 负载均衡
AI_MODELS=[{"api_key":"sk-xxx","base_url":"https://api1.com/v1","models":["glm-4-flash"]}]
AI_ENABLE_LOAD_BALANCING=true

# AI 队列
AI_QUEUE_ENABLED=true
AI_QUEUE_MAX_SIZE=20
AI_QUEUE_TIMEOUT=30

# Flask
FLASK_HOST=0.0.0.0
FLASK_PORT=4421
```

**Step 5: 创建 Dockerfile**

创建文件 `ai_end/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 4421

# 启动命令
CMD ["gunicorn", "--bind", "0.0.0.0:4421", "--workers", "2", "--timeout", "120", "app:app"]
```

**Step 6: Commit**

```bash
git add ai_end/
git commit -m "feat: 创建 ai_end 目录结构和基础文件"
```

---

## Task 2: 迁移 AI 负载均衡模块

**Files:**
- Create: `ai_end/services/load_balancer.py`
- Test: `ai_end/tests/test_load_balancer.py` (创建测试文件)

**Step 1: 复制并调整 load_balancer.py**

从 `backend/services/ai_load_balancer.py` 复制到 `ai_end/services/load_balancer.py`，修改 import 路径：

```python
"""AI模型负载均衡器。"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """单个模型配置。"""

    api_key: str
    base_url: str
    model: str
    _429_until: float = 0.0

    @property
    def is_available(self) -> bool:
        return time.time() >= self._429_until

    def mark_429(self, cooldown_seconds: int = 60):
        self._429_until = time.time() + cooldown_seconds
        masked_key = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key) > 12 else "***"
        logger.warning(
            f"[429] 模型: {self.model} @ {self.base_url} | key: {masked_key} | 冷却: {cooldown_seconds}秒"
        )


class AILoadBalancer:
    """AI模型负载均衡器。"""

    def __init__(self, models_config: list[dict]):
        self.models: list[ModelConfig] = []
        self.current_index = 0
        self.lock = threading.Lock()

        for config in models_config:
            api_key = config.get("api_key")
            base_url = config.get("base_url")
            models = config.get("models", [])

            if not api_key or not base_url or not models:
                logger.warning(f"跳过无效配置: {config}")
                continue

            for model_name in models:
                self.models.append(
                    ModelConfig(api_key=api_key, base_url=base_url, model=model_name)
                )

        logger.info(f"负载均衡器初始化完成，共 {len(self.models)} 个模型配置")

    def get_next_model(self) -> Optional[ModelConfig]:
        with self.lock:
            if not self.models:
                return None

            attempts = 0
            start_index = self.current_index

            while attempts < len(self.models):
                model_config = self.models[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.models)

                if model_config.is_available:
                    return model_config

                attempts += 1
                if self.current_index == start_index:
                    break

            logger.warning("所有模型配置均不可用（都在429冷却中）")
            return None

    def mark_model_429(self, model: Optional[ModelConfig], cooldown_seconds: int = 60) -> None:
        if model:
            model.mark_429(cooldown_seconds)
```

**Step 2: 创建测试目录和测试文件**

```bash
mkdir -p ai_end/tests
touch ai_end/tests/__init__.py
```

创建 `ai_end/tests/test_load_balancer.py`:

```python
"""负载均衡器测试。"""

import pytest
from ai_end.services.load_balancer import AILoadBalancer, ModelConfig


def test_single_model_config():
    config = [
        {"api_key": "sk-test", "base_url": "https://api.example.com/v1", "models": ["gpt-3.5"]}
    ]
    balancer = AILoadBalancer(config)
    model = balancer.get_next_model()
    assert model is not None
    assert model.model == "gpt-3.5"


def test_multiple_models():
    config = [
        {"api_key": "sk-test1", "base_url": "https://api1.com/v1", "models": ["model1"]},
        {"api_key": "sk-test2", "base_url": "https://api2.com/v1", "models": ["model2"]},
    ]
    balancer = AILoadBalancer(config)
    models = [balancer.get_next_model() for _ in range(4)]
    # 应该轮询选择
    assert models[0].model == "model1"
    assert models[1].model == "model2"
    assert models[2].model == "model1"
```

**Step 3: 运行测试验证**

```bash
cd ai_end && python -m pytest tests/test_load_balancer.py -v
```

**Step 4: Commit**

```bash
git add ai_end/services/load_balancer.py ai_end/tests/
git commit -m "feat: 迁移 AI 负载均衡模块"
```

---

## Task 3: 迁移 AI 队列模块

**Files:**
- Create: `ai_end/services/queue.py`

**Step 1: 复制并调整 queue.py**

从 `backend/services/ai_queue.py` 复制到 `ai_end/services/queue.py`，修改 import 路径：

```python
"""AI请求消息队列处理器。"""

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from flask import Flask

logger = logging.getLogger(__name__)


@dataclass
class QueueRequest:
    """队列中的请求项。"""

    request_id: str
    data: dict[str, Any]
    result_future: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class AIRequestQueue:
    """AI请求消息队列。"""

    def __init__(self, app: Flask, max_size: int = 20, timeout: int = 30):
        self.app = app
        self.queue = queue.Queue(maxsize=max_size)
        self.timeout = timeout
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False
        self.request_handler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None

    def set_handler(self, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.request_handler = handler

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(
            target=self._process_queue, daemon=True, name="AIQueueWorker"
        )
        self.worker_thread.start()
        logger.info("AI请求队列工作线程已启动")

    def stop(self) -> None:
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("AI请求队列工作线程已停止")

    def enqueue(
        self, request_data: dict[str, Any]
    ) -> tuple[bool, str | dict[str, Any]]:
        if not self.running:
            return False, "队列未启动"

        try:
            result_holder = {"done": False, "result": None, "error": None}
            event = threading.Event()

            req = QueueRequest(
                request_id=f"{threading.get_ident()}_{int(time.time() * 1000)}",
                data=request_data,
                result_future={"event": event, "holder": result_holder},
            )

            self.queue.put(req, block=True, timeout=5)
            logger.info(f"请求 {req.request_id} 已入队，当前队列深度: {self.queue.qsize()}")

            if event.wait(timeout=self.timeout):
                if result_holder["error"]:
                    return False, result_holder["error"]
                return True, result_holder["result"]
            else:
                return False, "请求处理超时"

        except queue.Full:
            logger.warning("AI请求队列已满，拒绝新请求")
            return False, "服务繁忙，请稍后再试"
        except Exception as e:
            logger.error(f"入队异常: {e}")
            return False, f"请求入队失败: {str(e)}"

    def _process_queue(self) -> None:
        while self.running:
            try:
                try:
                    req: QueueRequest = self.queue.get(block=True, timeout=1)
                except queue.Empty:
                    continue

                logger.info(f"开始处理请求 {req.request_id}")
                start_time = time.time()

                try:
                    with self.app.app_context():
                        result = self._handle_request(req)

                    elapsed = time.time() - start_time
                    logger.info(f"请求 {req.request_id} 处理完成，耗时 {elapsed:.2f}s")

                    future = req.result_future
                    future["holder"]["done"] = True
                    future["holder"]["result"] = result
                    future["event"].set()

                except Exception as e:
                    logger.error(f"处理请求 {req.request_id} 失败: {e}")
                    future = req.result_future
                    future["holder"]["done"] = True
                    future["holder"]["error"] = str(e)
                    future["event"].set()

                finally:
                    self.queue.task_done()

            except Exception as e:
                logger.error(f"工作线程异常: {e}")

    def _handle_request(self, req: QueueRequest) -> dict[str, Any]:
        if self.request_handler is None:
            return {"error": "未设置请求处理器"}

        return self.request_handler(req.data)

    def get_stats(self) -> dict[str, Any]:
        return {
            "queue_size": self.queue.qsize(),
            "queue_max_size": self.queue.maxsize,
            "running": self.running,
        }
```

**Step 2: Commit**

```bash
git add ai_end/services/queue.py
git commit -m "feat: 迁移 AI 队列模块"
```

---

## Task 4: 创建 ai_end 核心应用 (app.py)

**Files:**
- Create: `ai_end/app.py`

**Step 1: 创建 app.py**

这是最重要的文件，整合所有 AI 逻辑：

```python
"""AI 服务主应用。"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from typing import Any, Iterable, TypedDict, Annotated, Optional

from flask import Flask, jsonify, request
import requests
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from ai_end.config import Config
from ai_end.services.load_balancer import AILoadBalancer, ModelConfig
from ai_end.services.queue import AIRequestQueue

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建 Flask 应用
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# 配置
config = Config()

# 数据库连接（复用 backend 的 db 模块）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from backend.db import db_session

# Redis 缓存
redis_client = None
try:
    import redis
    redis_client = redis.Redis(
        host=config.redis_host,
        port=config.redis_port,
        db=config.redis_db,
        password=config.redis_password,
        decode_responses=True
    )
    redis_client.ping()
    logger.info("Redis 连接成功")
except Exception as e:
    logger.warning(f"Redis 连接失败: {e}")

cache = None
if redis_client:
    from backend.utils.redis_cache import RedisCache
    cache = RedisCache(redis_client)

# 负载均衡器单例
_load_balancer: Optional[AILoadBalancer] = None
_load_balancer_lock = threading.Lock()

# 消息队列单例
_ai_queue: Optional[AIRequestQueue] = None
_queue_lock = threading.Lock()
_queue_initialized = False

MEMORY_TTL_SECONDS = 24 * 60 * 60
MEMORY_MAX_ITEMS = 5


def _get_load_balancer() -> Optional[AILoadBalancer]:
    global _load_balancer
    if _load_balancer is None:
        with _load_balancer_lock:
            if _load_balancer is None:
                if config.ai_enable_load_balancing and config.ai_models:
                    _load_balancer = AILoadBalancer(config.ai_models)
                    logger.info(f"AI负载均衡器已启用，共 {len(config.ai_models)} 个配置组")
                else:
                    logger.debug("AI负载均衡器未启用或配置为空")
    return _load_balancer


def _create_llm_with_config(model_config: Optional[ModelConfig]) -> ChatOpenAI:
    if model_config:
        masked_key = f"{model_config.api_key[:8]}...{model_config.api_key[-4:]}" if len(model_config.api_key) > 12 else "***"
        logger.info(f"使用负载均衡模型: {model_config.model} @ {model_config.base_url} (key: {masked_key})")

        return ChatOpenAI(
            api_key=model_config.api_key,
            base_url=_normalize_ai_base_url(model_config.base_url),
            model=model_config.model,
            temperature=0.2,
        )

    masked_key = f"{config.api_key[:8]}...{config.api_key[-4:]}" if len(config.api_key) > 12 else "***"
    logger.info(f"使用传统单一配置: {config.ai_model} @ {config.ai_base_url} (key: {masked_key})")

    return ChatOpenAI(
        api_key=config.api_key,
        base_url=_normalize_ai_base_url(config.ai_base_url),
        model=config.ai_model,
        temperature=0.2,
    )


def _create_llm_for_request() -> tuple[Optional[ModelConfig], ChatOpenAI]:
    load_balancer = _get_load_balancer()
    if load_balancer:
        model_config = load_balancer.get_next_model()
        if model_config:
            masked_key = f"{model_config.api_key[:8]}...{model_config.api_key[-4:]}" if len(model_config.api_key) > 12 else "***"
            logger.info(f"使用负载均衡模型: {model_config.model} @ {model_config.base_url} (key: {masked_key})")

            llm = ChatOpenAI(
                api_key=model_config.api_key,
                base_url=_normalize_ai_base_url(model_config.base_url),
                model=model_config.model,
                temperature=0.2,
            )
            return model_config, llm
        raise RuntimeError("所有AI模型均不可用，请稍后再试。")

    if not (config.api_key and config.ai_base_url and config.ai_model):
        raise RuntimeError("AI服务配置不完整")

    masked_key = f"{config.api_key[:8]}...{config.api_key[-4:]}" if len(config.api_key) > 12 else "***"
    logger.info(f"使用传统单一配置: {config.ai_model} @ {config.ai_base_url} (key: {masked_key})")

    llm = ChatOpenAI(
        api_key=config.api_key,
        base_url=_normalize_ai_base_url(config.ai_base_url),
        model=config.ai_model,
        temperature=0.2,
    )
    return None, llm


def _is_rate_limit_error(error: Exception) -> bool:
    error_msg = str(error).lower()
    return (
        "429" in error_msg
        or "rate limit" in error_msg
        or "rate_limit" in error_msg
        or "too many requests" in error_msg
        or "quota" in error_msg
    )


def _is_ai_configured() -> bool:
    load_balancer = _get_load_balancer()
    if load_balancer and load_balancer.models:
        return True
    return bool(config.ai_base_url and config.api_key and config.ai_model)


def _normalize_ai_base_url(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url:
        return None
    url = raw_url.rstrip("/")
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def _log_messages(stage: str, messages: list[BaseMessage]) -> None:
    msg_types = {}
    for msg in messages:
        msg_type = msg.__class__.__name__
        msg_types[msg_type] = msg_types.get(msg_type, 0) + 1

    user_question_preview = ""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                user_question_preview = content[:50] + "..." if len(content) > 50 else content
            break

    logger.info(
        "AI请求 %s - 消息数: %d, 类型: %s, 问题: %s",
        stage,
        len(messages),
        json.dumps(msg_types, ensure_ascii=False),
        user_question_preview,
    )


def generate_embedding(text: str) -> Optional[list[float]]:
    """生成文本的向量嵌入。"""
    try:
        if config.embed_base_url and config.embed_api_key:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.embed_api_key}"
            }
            payload = {
                "model": config.embed_model or "default-model",
                "input": text
            }

            response = requests.post(config.embed_base_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()
            return result["data"][0]["embedding"]
        else:
            logger.error("嵌入服务配置不完整")
            return None

    except Exception as e:
        logger.error(f"生成向量嵌入失败: {e}")
        return None


def search_similar_articles(query_embedding: list[float], top_k: int = 3) -> list[dict[str, Any]]:
    """搜索与查询向量相似的文章。"""
    try:
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

        recency_weight = max(config.ai_recency_weight, 0.0)
        half_life_days = max(config.ai_recency_half_life_days, 1.0)
        candidate_limit = min(max(top_k * 5, top_k), 50)

        sql = """
        WITH candidate AS (
            SELECT a.id, a.title, a.unit, a.published_on, a.summary, a.content,
                   v.embedding <=> %s::vector AS similarity
            FROM vectors v
            JOIN articles a ON v.article_id = a.id
            ORDER BY v.embedding <=> %s::vector
            LIMIT %s
        )
        SELECT id, title, unit, published_on, summary, content, similarity,
               similarity - %s * exp(-GREATEST(CURRENT_DATE - published_on, 0)::float / %s) AS score
        FROM candidate
        ORDER BY score ASC
        LIMIT %s
        """
        params: list[Any] = [vector_str, vector_str, candidate_limit, recency_weight, half_life_days, top_k]

        with db_session() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            results = cur.fetchall()

        articles = []
        for row in results:
            article = {
                "id": row["id"],
                "title": row["title"],
                "unit": row["unit"],
                "published_on": row["published_on"],
                "summary": row["summary"],
                "content": row["content"],
                "similarity": float(row["similarity"]),
                "score": float(row["score"])
            }
            articles.append(article)

        return articles

    except Exception as e:
        logger.error(f"搜索相似文章失败: {e}")
        return []


def _memory_key(user_id: str) -> str:
    return f"ai:mem:{user_id}"


def _load_short_memory(user_id: str) -> list[dict[str, str]]:
    if not cache:
        return []
    raw = cache.get(_memory_key(user_id), default=[])
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _save_short_memory(user_id: str, question: str, answer: str) -> None:
    if not cache:
        return
    history = _load_short_memory(user_id)
    history.append({"user": question, "assistant": answer})
    history = history[-MEMORY_MAX_ITEMS:]
    cache.set(_memory_key(user_id), history, expire_seconds=MEMORY_TTL_SECONDS)


def _build_memory_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        user_text = (item.get("user") or "").strip()
        assistant_text = (item.get("assistant") or "").strip()
        if user_text:
            messages.append(HumanMessage(content=user_text))
        if assistant_text:
            messages.append(AIMessage(content=assistant_text))
    return messages


def _build_system_prompt(top_k_hint: int, display_name: Optional[str] = None) -> str:
    time_now = datetime.now()
    identity_hint = f"当前用户的名字：{display_name}。可酌情称呼，但不强制。\n" if display_name else "\n"
    return (
        f"""
你是校内OA管理员瑞德，专注于帮人查找和解读OA系统中的相关文章。你会根据问题的具体需求，自主判断是否需要检索文章内容来为你提供准确信息。
**你的工作方式：**
1. **常规问题**：如果用户的提问不涉及具体文章内容（例如流程咨询、功能指引），你会直接基于知识作答。
2. **文章查询**：当问题涉及具体政策、通知、文章细节时，你会主动检索相关文章，确保信息准确。
3. **检索设置**：检索时要根据问题复杂度自动选择：
   - **简要检索** (`detail_level: brief`)：适用于关键词查询、简单事实确认。
   - **全文检索** (`detail_level: full`)：适用于复杂分析、政策解读或多文章对比。
   - **检索数量** (`top_k`)：通常设置为 `{top_k_hint}` 篇左右，确保覆盖核心内容，如果返回的结果你认为无法覆盖，你将会进行下一次搜索，最多多搜索一次。
**！！注意：**
- 你要严格依据OA系统内现有信息作答，不编造未收录的内容。
- 如需深入分析，建议用户提供具体的关键词或背景，你会更精准地定位文章。
- 如果用户的问题与OA系统无关，你会礼貌提醒并引导其关注相关事务。
{identity_hint}
当前日期和时间：{time_now.strftime("%Y年%m月%d日 %H:%M")}
"""
    )


@tool("vector_search")
def vector_search_tool(query: str, top_k: int = 3, detail_level: str = "brief") -> str:
    """OA向量检索工具：返回相关文章内容与摘要。"""
    normalized_top_k = max(1, min(10, int(top_k)))
    normalized_level = "full" if detail_level == "full" else "brief"
    logger.info(
        "AI工具调用 vector_search: %s",
        json.dumps(
            {"query": query, "top_k": normalized_top_k, "detail_level": normalized_level},
            ensure_ascii=False,
            default=str,
        ),
    )
    embedding = generate_embedding(query)
    if not embedding:
        payload = {"error": "embedding_failed", "documents": [], "related_articles": []}
        return json.dumps(payload, ensure_ascii=False)

    articles = search_similar_articles(embedding, normalized_top_k)
    related_articles = _build_related_articles(articles)
    documents = []
    for article in articles:
        doc = {
            "id": article.get("id"),
            "title": article.get("title"),
            "unit": article.get("unit"),
            "published_on": _serialize_value(article.get("published_on")),
            "summary": article.get("summary"),
        }
        if normalized_level == "full":
            doc["content"] = article.get("content") or ""
        else:
            doc["content_snippet"] = _truncate_text(article.get("content"))
            doc["summary_snippet"] = _truncate_text(article.get("summary"))
        documents.append(doc)

    payload = {
        "detail_level": normalized_level,
        "documents": documents,
        "related_articles": related_articles,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, default=str)
    logger.info(
        "AI工具返回 vector_search: %s",
        json.dumps(
            {"len": len(payload_text), "preview": payload_text[:500]},
            ensure_ascii=False,
            default=str,
        ),
    )
    return payload_text


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _build_agent_with_config(fixed_model_config: Optional[ModelConfig]) -> Any:
    tools = [vector_search_tool]
    llm = _create_llm_with_config(fixed_model_config)
    llm_with_tools = llm.bind_tools(tools)

    initial_config = fixed_model_config

    def agent_node(state: AgentState) -> dict[str, list[BaseMessage]]:
        load_balancer = _get_load_balancer()
        max_tries = len(load_balancer.models) if load_balancer else 1
        last_error: Optional[Exception] = None

        for attempt in range(max_tries):
            try:
                if attempt == 0:
                    current_llm_config = initial_config
                else:
                    current_llm_config, _ = _create_llm_for_request()

                current_llm = _create_llm_with_config(current_llm_config)
                current_llm_with_tools = current_llm.bind_tools(tools)

                _log_messages("before_llm", state["messages"])
                response = current_llm_with_tools.invoke(state["messages"])
                _log_messages("after_llm", state["messages"] + [response])

                return {"messages": state["messages"] + [response]}

            except Exception as e:
                last_error = e
                is_rate_limit = _is_rate_limit_error(e)

                if attempt == 0:
                    if initial_config:
                        masked_key = f"{initial_config.api_key[:8]}...{initial_config.api_key[-4:]}" if len(initial_config.api_key) > 12 else "***"
                        model_info = f"模型: {initial_config.model} @ {initial_config.base_url} (key: {masked_key})"
                    else:
                        model_info = f"传统配置: {config.ai_model} @ {config.ai_base_url}"
                else:
                    model_info = "重试模型"

                if is_rate_limit and load_balancer and attempt < max_tries - 1:
                    if attempt == 0 and initial_config:
                        logger.warning(f"[429] {model_info} - 切换模型重试 (尝试 {attempt + 1}/{max_tries})")
                        load_balancer.mark_model_429(initial_config)
                    else:
                        logger.warning(f"[429] {model_info} - 继续切换模型重试 (尝试 {attempt + 1}/{max_tries})")
                    continue
                else:
                    logger.error(f"[AI请求失败] {model_info} - 错误: {e}")
                    raise

        if last_error:
            raise last_error
        raise Exception("所有AI模型均不可用，请稍后再试")

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")
    return graph.compile()


def _extract_related_articles(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        items = payload.get("related_articles")
        if isinstance(items, list):
            related = items
    return related


def _extract_answer(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            if getattr(message, "tool_calls", None):
                continue
            return message.content
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            return message.content
    return ""


def _truncate_text(text: Optional[str], limit: int = 80) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}…"


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    return value


def _build_related_articles(articles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    related = []
    for article in articles:
        content_snippet = _truncate_text(article.get("content"))
        summary_snippet = _truncate_text(article.get("summary"))
        related.append(
            {
                "id": article.get("id"),
                "title": article.get("title"),
                "unit": article.get("unit"),
                "published_on": _serialize_value(article.get("published_on")),
                "similarity": article.get("similarity"),
                "content_snippet": content_snippet,
                "summary_snippet": summary_snippet,
            }
        )
    return related


def _initialize_queue() -> None:
    global _ai_queue, _queue_initialized
    if _queue_initialized:
        return
    if config.ai_queue_enabled:
        _ai_queue = AIRequestQueue(
            app=app,
            max_size=config.ai_queue_max_size,
            timeout=config.ai_queue_timeout,
        )
        _ai_queue.set_handler(_process_ai_request_internal)
        _ai_queue.start()
        _queue_initialized = True
        logger.info("AI请求队列已启动")


def _process_ai_request_internal(data: dict[str, Any]) -> dict[str, Any]:
    question = data.get("question")
    top_k_hint = data.get("top_k", 3)
    display_name = data.get("display_name")
    user_id = data.get("user_id", "")

    if not _is_ai_configured():
        return {"error": "AI服务配置不完整"}

    model_config_for_this_request: Optional[ModelConfig] = None
    load_balancer = _get_load_balancer()
    if load_balancer and load_balancer.models:
        model_config_for_this_request = load_balancer.get_next_model()

    history = _load_short_memory(user_id) if user_id else []
    messages: list[BaseMessage] = [
        SystemMessage(content=_build_system_prompt(top_k_hint, display_name)),
        *_build_memory_messages(history),
        HumanMessage(content=question),
    ]

    agent = _build_agent_with_config(model_config_for_this_request)
    result = agent.invoke({"messages": messages})
    final_messages = result.get("messages", messages)
    answer = _extract_answer(final_messages) or "当前服务不可用，请稍后再试。"
    related_articles = _extract_related_articles(final_messages)

    if user_id:
        _save_short_memory(user_id, question, answer)

    return {"answer": answer, "related_articles": related_articles}


@app.route('/ask', methods=['POST'])
def ask_question():
    """AI问答API。"""
    try:
        data = request.get_json()

        if not data or 'question' not in data:
            return jsonify({"error": "请求参数错误，缺少question字段"}), 400

        question = data['question']
        top_k_hint = data.get('top_k', 3)
        display_name = data.get('display_name')

        if not _is_ai_configured():
            return jsonify({"error": "AI服务配置不完整"}), 500

        user_id = data.get('user_id', '')

        # 检查是否使用队列
        if _ai_queue and config.ai_queue_enabled:
            queue_data = {
                "question": question,
                "top_k": top_k_hint,
                "display_name": display_name,
                "user_id": user_id,
            }

            logger.info(
                "AI请求入队: %s",
                json.dumps(
                    {"question": question, "user_id": user_id, "queue_enabled": True},
                    ensure_ascii=False,
                ),
            )

            success, result = _ai_queue.enqueue(queue_data)
            if not success:
                return jsonify({"error": result}), 503

            return jsonify(result), 200
        else:
            model_config_for_this_request: Optional[ModelConfig] = None
            load_balancer = _get_load_balancer()
            if load_balancer and load_balancer.models:
                model_config_for_this_request = load_balancer.get_next_model()

            history = _load_short_memory(user_id) if user_id else []

            messages: list[BaseMessage] = [
                SystemMessage(content=_build_system_prompt(top_k_hint, display_name)),
                *_build_memory_messages(history),
                HumanMessage(content=question),
            ]

            agent = _build_agent_with_config(model_config_for_this_request)
            result = agent.invoke({"messages": messages})
            final_messages = result.get("messages", messages)
            answer = _extract_answer(final_messages) or "当前服务不可用，请稍后再试。"
            related_articles = _extract_related_articles(final_messages)

            if user_id:
                _save_short_memory(user_id, question, answer)

            return jsonify({"answer": answer, "related_articles": related_articles}), 200

    except Exception as e:
        logger.error(f"AI问答失败: {e}")
        return jsonify({"error": "AI问答失败"}), 500


@app.route('/clear_memory', methods=['POST'])
def clear_memory():
    """清空用户的AI短记忆缓存。"""
    try:
        data = request.get_json()
        user_id = data.get('user_id') if data else None

        if not user_id:
            return jsonify({"error": "用户信息缺失"}), 400

        if cache:
            cleared = cache.delete(_memory_key(user_id))
        else:
            cleared = True

        logger.info("AI记忆清理: %s", json.dumps({"user_id": user_id, "cleared": cleared}, ensure_ascii=False))
        return jsonify({"cleared": bool(cleared)}), 200
    except Exception as e:
        logger.error(f"AI记忆清理失败: {e}")
        return jsonify({"error": "AI记忆清理失败"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查。"""
    return jsonify({"status": "ok"}), 200


# 启动时初始化队列
@app.before_request
def init_queue_once():
    global _queue_initialized
    if not _queue_initialized:
        _initialize_queue()
        _queue_initialized = True


if __name__ == '__main__':
    app.run(host=config.flask_host, port=config.flask_port, debug=False)
```

**Step 2: Commit**

```bash
git add ai_end/app.py
git commit -m "feat: 创建 ai_end 核心应用"
```

---

## Task 5: 修改 backend 移除 AI 配置

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/.env.example`

**Step 1: 修改 backend/config.py**

从 `backend/config.py` 中移除 AI 相关配置（第 36-54 行）：

```python
# 删除以下配置项：
# self.embed_base_url
# self.embed_model
# self.embed_api_key
# self.embed_dim
# self.ai_base_url
# self.ai_model
# self.api_key
# self.ai_vector_limit_days
# self.ai_vector_limit_count
# self.ai_recency_half_life_days
# self.ai_recency_weight
# self.ai_models
# self.ai_enable_load_balancing
# self.ai_queue_enabled
# self.ai_queue_max_size
# self.ai_queue_timeout
```

同时删除 `_override_with_environment` 方法中的对应 key 列表中的 AI 相关项。

**Step 2: 修改 backend/.env.example**

移除 AI 相关配置项。

**Step 3: Commit**

```bash
git add backend/config.py backend/.env.example
git commit -m "feat: backend 移除 AI 配置"
```

---

## Task 6: 修改 backend 调用 ai_end API

**Files:**
- Modify: `backend/routes/ai.py`

**Step 1: 替换 backend/routes/ai.py**

将原来的 AI 逻辑替换为调用 ai_end API：

```python
"""AI问答API路由模块。

该模块将请求转发给 ai_end 服务处理。
"""

from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request
import requests

from backend.config import Config
from backend.routes.auth import login_required

# 初始化蓝图
bp = Blueprint('ai', __name__)

# 设置日志
logger = logging.getLogger(__name__)

# 配置
config = Config()

# ai_end 服务地址（从环境变量读取）
AI_END_URL = config.ai_end_url or "http://localhost:4421"


def _get_ai_end_url() -> str:
    """获取 ai_end 服务地址。"""
    return AI_END_URL


def _forward_to_ai_end(endpoint: str, data: dict) -> tuple[dict, int]:
    """转发请求到 ai_end 服务。

    Args:
        endpoint: API 端点（不含前缀）
        data: 请求数据

    Returns:
        (响应数据, HTTP状态码)
    """
    url = f"{_get_ai_end_url()}/{endpoint}"
    try:
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"调用 ai_end 服务失败: {e}")
        return {"error": "AI服务不可用"}, 503


@bp.route('/ask', methods=['POST'])
@login_required
def ask_question():
    """基于向量的问答API（转发到 ai_end）。

    请求体：
        {"question": "你的问题", "top_k": 3, "display_name": "张三"}

    返回：
        包含回答和相关文章的JSON响应
    """
    try:
        data = request.get_json()

        if not data or 'question' not in data:
            return jsonify({"error": "请求参数错误，缺少question字段"}), 400

        question = data['question']
        top_k_hint = data.get('top_k', 3)
        display_name = data.get('display_name')

        # 获取用户信息
        user_claims = getattr(request, "auth_claims", {})
        user_id = str(user_claims.get("sub") or "")

        # 转发到 ai_end
        ai_data = {
            "question": question,
            "top_k": top_k_hint,
            "display_name": display_name,
            "user_id": user_id,
        }

        result, status_code = _forward_to_ai_end("ask", ai_data)
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"AI问答转发失败: {e}")
        return jsonify({"error": "AI问答失败"}), 500


@bp.route('/clear_memory', methods=['POST'])
@login_required
def clear_memory():
    """清空用户的AI短记忆缓存（转发到 ai_end）。"""
    try:
        user_claims = getattr(request, "auth_claims", {})
        user_id = str(user_claims.get("sub") or "")

        if not user_id:
            return jsonify({"error": "用户信息缺失"}), 400

        result, status_code = _forward_to_ai_end("clear_memory", {"user_id": user_id})
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"AI记忆清理转发失败: {e}")
        return jsonify({"error": "AI记忆清理失败"}), 500


@bp.route('/embed', methods=['POST'])
@login_required
def create_embedding():
    """生成文本的向量嵌入（转发到 ai_end）。

    请求体：
        {"text": "要生成嵌入的文本"}

    返回：
        包含向量嵌入的JSON响应
    """
    try:
        data = request.get_json()

        if not data or 'text' not in data:
            return jsonify({"error": "请求参数错误，缺少text字段"}), 400

        text = data['text']

        # 转发到 ai_end
        result, status_code = _forward_to_ai_end("embed", {"text": text})
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"生成向量嵌入转发失败: {e}")
        return jsonify({"error": "生成向量嵌入失败"}), 500
```

**Step 2: 添加 ai_end_url 配置到 backend/config.py**

在 backend/config.py 中添加：

```python
# AI End 服务地址
self.ai_end_url: Optional[str] = None
```

并在 `_override_with_environment` 中添加：

```python
elif key == "AI_END_URL":
    self.ai_end_url = value or None
```

**Step 3: Commit**

```bash
git add backend/routes/ai.py backend/config.py
git commit -m "feat: backend 改为调用 ai_end API"
```

---

## Task 7: 验证和测试

**Step 1: 创建 docker-compose 集成测试**

在项目根目录创建或更新 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "4420:4420"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/oap
      - REDIS_HOST=redis
      - AI_END_URL=http://ai_end:4421
    depends_on:
      - db
      - redis
      - ai_end

  ai_end:
    build: ./ai_end
    ports:
      - "4421:4421"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/oap
      - REDIS_HOST=redis
    depends_on:
      - db
      - redis

  db:
    image: pgvector/pgvector:pg16
    # ...

  redis:
    image: redis:7
    # ...
```

**Step 2: 测试后端调用**

```bash
# 启动服务
docker-compose up -d

# 测试 AI 问答
curl -X POST http://localhost:4420/ai/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"question": "测试问题"}'
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: 添加 docker-compose 集成配置"
```

---

## 计划完成

实施计划已保存到 `docs/plans/2026-03-15-ai-endpoint-separation-design.md`

---

**Two execution options:**

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

2. **Parallel Session (separate)** - Open new session with executing_plans, batch execution with checkpoints

**Which approach?**
