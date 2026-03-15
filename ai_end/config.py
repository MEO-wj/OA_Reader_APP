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
