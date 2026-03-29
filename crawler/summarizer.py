"""OA 系统文章 AI 摘要生成模块。

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
    """调用 AI API 发送摘要请求。"""
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
    """从 AI API 响应中提取摘要文本。"""
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    text = choices[-1]["message"].get("content", "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    text = text.lstrip("# ").lstrip()
    return text


class Summarizer:
    """AI 摘要生成器类。

    支持主力/兜底两级模型策略：
    1. 优先使用主力模型
    2. 任何失败触发兜底重试
    3. 兜底也失败则返回 None
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()

    def summarize(self, content: str) -> str | None:
        """为给定的文章内容生成 AI 摘要。"""
        balancer = _get_load_balancer(self.config)

        if balancer:
            return self._summarize_with_fallback(balancer, content)

        return self._summarize_single(content)

    def _summarize_with_fallback(self, balancer: PrimaryFallbackBalancer, content: str) -> str | None:
        """主力/兜底两级模型策略。"""
        # 尝试主力模型
        primary = balancer.get_model()
        result = self._try_model(primary, content, balancer)
        if result is not None:
            return result

        logger.warning("主力模型失败，切换到兜底模型")

        # 主力失败，尝试兜底模型
        fallback = balancer.get_fallback()
        return self._try_model(fallback, content, balancer)

    def _try_model(self, model_config: ModelConfig, content: str, balancer: PrimaryFallbackBalancer | None = None) -> str | None:
        """尝试用指定模型生成摘要。"""
        resp = _call_ai(model_config, content)
        if resp is None:
            logger.warning("模型 %s 请求异常", model_config.model)
            return None

        if resp.status_code != 200:
            if _is_429_response(resp) and balancer:
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
