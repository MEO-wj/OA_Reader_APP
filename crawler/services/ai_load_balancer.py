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
