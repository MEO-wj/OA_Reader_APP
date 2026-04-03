"""聊天模块公共工具函数"""
import re


def _sanitize_memory_text(text: str) -> str:
    """
    清洗记忆文本，去除 markdown 格式和 think 标签

    Args:
        text: 原始文本

    Returns:
        清洗后的文本
    """
    if not text:
        return ""

    cleaned = text

    # 去除 markdown 代码块标记
    cleaned = re.sub(r"^```[a-z]*\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^```", "", cleaned, flags=re.MULTILINE)

    # 去除各种 think 标签
    cleaned = re.sub(r"<\/?think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = cleaned.replace("**", "")

    lines: list[str] = []
    for raw in cleaned.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in {"#", "##", "###", "---", "___", "***"}:
            continue
        lines.append(line)

    return "\n".join(lines).strip()
