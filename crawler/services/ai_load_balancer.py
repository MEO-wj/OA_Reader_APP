"""AI模型负载均衡器（爬虫端）。

实现轮询式负载均衡 + 429错误自动冷却。
支持多个API密钥和模型组合的轮询调度。
"""

from __future__ import annotations

import logging
import threading
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
        """标记该配置为429状态，设置冷却时间。

        Args:
            cooldown_seconds: 冷却时间（秒），默认60秒
        """
        self._429_until = time.time() + cooldown_seconds
        masked_key = _mask_key(self.api_key)
        logger.warning(
            "[429] 模型: %s @ %s | key: %s | 冷却: %s秒",
            self.model,
            self.base_url,
            masked_key,
            cooldown_seconds,
        )


class AILoadBalancer:
    """AI模型负载均衡器。

    支持多个（api_key, model）组合的轮询调度，
    自动跳过处于429冷却期的配置。
    """

    def __init__(self, models_config: list[dict]):
        """初始化负载均衡器。

        Args:
            models_config: 模型配置列表，每个配置包含 api_key、base_url 和 models 列表

        models_config 格式:
        [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1/chat/completions", "models": ["glm-4-flash"]},
            {"api_key": "sk-key2", "base_url": "https://api2.com/v1/chat/completions", "models": ["qwen-max"]},
        ]
        """
        self.models: list[ModelConfig] = []
        self.current_index = 0
        self.lock = threading.Lock()

        for config in models_config:
            api_key = config.get("api_key")
            base_url = config.get("base_url")
            models = config.get("models", [])

            if not api_key or not base_url or not models:
                logger.warning("跳过无效配置: %s", config)
                continue

            for model_name in models:
                self.models.append(
                    ModelConfig(api_key=api_key, base_url=base_url, model=model_name)
                )

        logger.info("负载均衡器初始化完成，共 %s 个模型配置", len(self.models))

    def get_next_model(self) -> Optional[ModelConfig]:
        """获取下一个可用模型配置（轮询 + 跳过429的配置）。"""
        with self.lock:
            if not self.models:
                return None

            attempts = 0
            start_index = self.current_index

            while attempts < len(self.models):
                model_config = self.models[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.models)

                if model_config.is_available:
                    logger.debug(
                        "选择模型: %s @ %s (索引: %s)",
                        model_config.model,
                        model_config.base_url,
                        self.current_index - 1,
                    )
                    return model_config

                attempts += 1
                if self.current_index == start_index:
                    break

            logger.warning("所有模型配置均不可用（都在429冷却中）")
            return None

    def mark_model_429(self, model: ModelConfig | None, cooldown_seconds: int = 60) -> None:
        """标记指定模型为429状态。"""
        if model:
            model.mark_429(cooldown_seconds)


def _mask_key(api_key: str) -> str:
    if not api_key:
        return "***"
    if len(api_key) <= 12:
        return "***"
    return f"{api_key[:8]}...{api_key[-4:]}"
