from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Optional


class Config:
    """后端配置加载器（仅包含后端所需字段）。"""

    def __init__(self, env_file: str | Path | None = None) -> None:
        self.project_root = Path(__file__).resolve().parents[1]
        default_env = Path(__file__).resolve().parent / ".env"
        self.env_file = self._resolve_path(env_file) if env_file else default_env

        # 默认值
        self.database_url: Optional[str] = None
        self.auth_access_token_ttl: timedelta = timedelta(days=7)
        self.auth_refresh_token_ttl: timedelta = timedelta(days=7)
        self.auth_jwt_secret: Optional[str] = None
        self.auth_password_cost: int = 12
        self.auth_refresh_hash_key: Optional[str] = None
        self.auth_allow_auto_user_creation: bool = True
        self.campus_auth_enabled: bool = True
        self.campus_auth_url: Optional[str] = "http://a.stu.edu.cn/ac_portal/login.php"
        self.campus_auth_timeout: int = 10  # seconds
        self.redis_host: str = "localhost"
        self.redis_port: int = 6379
        self.redis_db: int = 0
        self.redis_password: Optional[str] = None
        self.cors_allow_origins: list[str] = ["*"]
        self.rate_limit_per_day: Optional[int] = None
        self.rate_limit_per_hour: Optional[int] = None
        # AI End 服务地址
        self.ai_end_url: Optional[str] = "http://localhost:4421"

        self.load()

    # 加载逻辑
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
            "AUTH_ACCESS_TOKEN_TTL",
            "AUTH_REFRESH_TOKEN_TTL",
            "AUTH_JWT_SECRET",
            "AUTH_PASSWORD_COST",
            "AUTH_REFRESH_HASH_KEY",
            "AUTH_ALLOW_AUTO_USER_CREATION",
            "CAMPUS_AUTH_ENABLED",
            "CAMPUS_AUTH_URL",
            "CAMPUS_AUTH_TIMEOUT",
            "REDIS_HOST",
            "REDIS_PORT",
            "REDIS_DB",
            "REDIS_PASSWORD",
            "CORS_ALLOW_ORIGINS",
            "RATE_LIMIT_PER_DAY",
            "RATE_LIMIT_PER_HOUR",
            "AI_END_URL",
        ]
        for key in keys:
            value = os.getenv(key)
            if value is not None and value != "":
                self._apply_setting(key, value)

    def _apply_setting(self, key: str, raw_value: str) -> None:
        value = raw_value.strip()
        if key == "DATABASE_URL":
            self.database_url = value or None
        elif key == "AUTH_ACCESS_TOKEN_TTL":
            self.auth_access_token_ttl = self._parse_ttl(value, fallback=self.auth_access_token_ttl)
        elif key == "AUTH_REFRESH_TOKEN_TTL":
            self.auth_refresh_token_ttl = self._parse_ttl(value, fallback=self.auth_refresh_token_ttl)
        elif key == "AUTH_JWT_SECRET":
            self.auth_jwt_secret = value or None
        elif key == "AUTH_PASSWORD_COST":
            try:
                self.auth_password_cost = int(value)
            except ValueError:
                pass
        elif key == "AUTH_REFRESH_HASH_KEY":
            self.auth_refresh_hash_key = value or None
        elif key == "AUTH_ALLOW_AUTO_USER_CREATION":
            self.auth_allow_auto_user_creation = value.lower() in ("1", "true", "yes", "on")
        elif key == "CAMPUS_AUTH_ENABLED":
            self.campus_auth_enabled = value.lower() in ("1", "true", "yes", "on")
        elif key == "CAMPUS_AUTH_URL":
            self.campus_auth_url = value or None
        elif key == "CAMPUS_AUTH_TIMEOUT":
            try:
                self.campus_auth_timeout = int(value)
            except ValueError:
                pass
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
        elif key == "CORS_ALLOW_ORIGINS":
            self.cors_allow_origins = [part.strip() for part in value.split(",") if part.strip()]
        elif key == "RATE_LIMIT_PER_DAY":
            try:
                limit = int(value)
                self.rate_limit_per_day = limit if limit > 0 else None
            except ValueError:
                pass
        elif key == "RATE_LIMIT_PER_HOUR":
            try:
                limit = int(value)
                self.rate_limit_per_hour = limit if limit > 0 else None
            except ValueError:
                pass
        elif key == "AI_END_URL":
            self.ai_end_url = value or None

    @staticmethod
    def _parse_ttl(raw: str, fallback: timedelta) -> timedelta:
        try:
            seconds = int(raw)
            return timedelta(seconds=seconds)
        except ValueError:
            return fallback


__all__ = ["Config"]
