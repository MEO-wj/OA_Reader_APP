"""AI模型负载均衡器。

实现轮询式负载均衡 + 429错误自动重试机制。
支持多个API密钥和模型组合的轮询调度。
"""

import logging
import threading
import time
from dataclasses import dataclass, field
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

    def mark_429(self, cooldown_seconds: int = 60):
        """标记该配置为429状态，设置冷却时间。

        Args:
            cooldown_seconds: 冷却时间（秒），默认60秒
        """
        self._429_until = time.time() + cooldown_seconds
        # 隐藏API Key显示（只显示前8位和后4位）
        masked_key = f"{self.api_key[:8]}...{self.api_key[-4:]}" if len(self.api_key) > 12 else "***"
        logger.warning(
            f"[429] 模型: {self.model} @ {self.base_url} | key: {masked_key} | 冷却: {cooldown_seconds}秒"
        )


class AILoadBalancer:
    """AI模型负载均衡器。

    支持多个（api_key, model）组合的轮询调度，
    自动跳过处于429冷却期的配置。

    使用示例:
        models_config = [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["glm-4-flash", "glm-4-plus"]},
            {"api_key": "sk-key2", "base_url": "https://api2.com/v1", "models": ["qwen-max"]},
        ]
        balancer = AILoadBalancer(models_config)
        config = balancer.get_next_model()
        if config:
            llm = ChatOpenAI(api_key=config.api_key, base_url=config.base_url, model=config.model)
    """

    def __init__(self, models_config: list[dict]):
        """初始化负载均衡器。

        Args:
            models_config: 模型配置列表，每个配置包含 api_key、base_url 和 models 列表

        models_config 格式:
        [
            {"api_key": "sk-key1", "base_url": "https://api1.com/v1", "models": ["glm-4-flash", "glm-4-plus"]},
            {"api_key": "sk-key2", "base_url": "https://api2.com/v1", "models": ["qwen-max"]},
        ]
        """
        self.models: list[ModelConfig] = []
        self.current_index = 0
        self.lock = threading.Lock()

        # 展开所有（api_key, model）组合
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
        """获取下一个可用模型配置（轮询 + 跳过429的配置）。

        Returns:
            可用的ModelConfig实例，如果所有配置都不可用则返回None
        """
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
                        f"选择模型: {model_config.model} @ {model_config.base_url} "
                        f"(索引: {self.current_index - 1})"
                    )
                    return model_config

                attempts += 1
                # 如果回到起点，说明遍历完了
                if self.current_index == start_index:
                    break

            logger.warning("所有模型配置均不可用（都在429冷却中）")
            return None

    def mark_model_429(
        self, model: ModelConfig | None, cooldown_seconds: int = 60
    ) -> None:
        """标记指定模型为429状态。

        Args:
            model: 要标记的模型配置
            cooldown_seconds: 冷却时间（秒），默认60秒
        """
        if model:
            model.mark_429(cooldown_seconds)
