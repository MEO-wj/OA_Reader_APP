"""
对话历史压缩模块

提供对话历史的 LLM 压缩功能，将长对话压缩成结构化摘要。
"""
import asyncio
import logging
from typing import Any

from openai import APIError

from src.config.settings import Config
from src.core.api_clients import get_llm_client
from src.chat.prompts_runtime import COMPACT_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


def _format_messages(messages: list[dict[str, Any]]) -> str:
    """
    将消息列表格式化为字符串。

    Args:
        messages: 消息列表

    Returns:
        格式化的字符串
    """
    formatted = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # 处理 tool_calls
        if msg.get("tool_calls"):
            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in msg["tool_calls"]]
            content = f"[工具调用: {', '.join(tool_names)}] {content}"

        # 处理 tool 角色
        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            content = f"[Tool {tool_call_id}] {content}"

        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)


async def compact_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Any]:
    """
    压缩对话历史，调用 LLM 生成精华摘要。

    Args:
        messages: 原始消息列表

    Returns:
        tuple[list[dict[str, Any]], Any]: (压缩后的消息列表, LLM 响应对象)
        - 消息列表格式：[{"role": "assistant", "content": "## 对话摘要\n...\n## 关键结论\n...\n## 待继续事项\n...\n## 用户画像\n..."}]
        - 响应对象包含 usage 数据，可用于追踪 token 消耗
        - 异常时返回 (原始消息, None)
    """
    # 空消息直接返回
    if not messages:
        return ([], None)

    # 格式化消息内容
    formatted_messages = _format_messages(messages)

    # 构建 Prompt
    prompt = COMPACT_PROMPT_TEMPLATE.format(messages=formatted_messages)

    # 获取配置
    config = Config.load()

    # 获取 LLM 客户端（复用单例）
    client = get_llm_client()

    try:
        # 调用 LLM（使用 asyncio.to_thread 包装同步调用）
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=config.llm_max_tokens,
            temperature=config.llm_temperature,
        )

        content = response.choices[0].message.content or ""

        # 返回结构化摘要和响应（用于 usage 追踪）
        return ([{"role": "assistant", "content": content}], response)

    except KeyboardInterrupt:
        # 用户中断时重新抛出，不捕获
        raise
    except APIError as e:
        # API 调用错误时，记录日志并返回原始消息
        logger.warning(f"对话压缩 API 错误: {e}，返回原始消息")
        return (messages, None)
    except Exception as e:
        # 其他异常（非 APIError）也返回原始消息
        logger.warning(f"对话压缩失败: {e}，返回原始消息")
        return (messages, None)
