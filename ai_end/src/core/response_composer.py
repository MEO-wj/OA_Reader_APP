"""回答组装模块

将检索到的文章上下文组装为 LLM 可消费的 prompt，并格式化来源引用。
"""
from __future__ import annotations

from typing import Any


class ResponseComposer:
    """将检索结果组装为最终回答。"""

    @staticmethod
    def format_context_block(
        articles: list[dict[str, Any]],
        detail_level: str = "brief",
    ) -> str:
        """将文章列表格式化为 context block。"""
        if not articles:
            return ""

        blocks = []
        for i, article in enumerate(articles, 1):
            block = (
                f"[文章{i}] 标题: {article.get('title', '')}\n"
                f"发布单位: {article.get('unit', '未知')}\n"
                f"发布日期: {article.get('published_on', '')}\n"
                f"摘要: {article.get('summary', '')}"
            )
            if detail_level == "full" and article.get("content"):
                block += f"\n内容: {article['content']}"
            blocks.append(block)

        return "\n---\n".join(blocks)

    @staticmethod
    def format_sources(articles: list[dict[str, Any]]) -> str:
        """格式化来源引用。"""
        if not articles:
            return ""

        lines = ["来源:"]
        for article in articles:
            title = article.get("title", "")
            unit = article.get("unit", "")
            date = article.get("published_on", "")
            lines.append(f"- 《{title}》 ({unit}, {date})")

        return "\n".join(lines)

    @staticmethod
    def compose(
        query: str,
        articles: list[dict[str, Any]],
        detail_level: str = "brief",
    ) -> str:
        """组装最终回答（context + sources）。"""
        context = ResponseComposer.format_context_block(articles, detail_level)
        sources = ResponseComposer.format_sources(articles)

        parts = []
        if context:
            parts.append(context)
        if sources:
            parts.append(sources)

        return "\n\n".join(parts)
