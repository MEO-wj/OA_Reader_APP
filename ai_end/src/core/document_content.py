"""document 内容处理模块

提供文档的获取、匹配策略、结果格式化功能。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from typing import Any

from src.core.db import get_pool


@dataclass
class MatchResult:
    """单个匹配结果。"""

    content: str
    line_number: int
    context_before: list[str]
    context_after: list[str]
    highlight_ranges: list[tuple[int, int]]


class Matcher(ABC):
    """匹配器抽象基类。"""

    @abstractmethod
    async def match(self, content: str, **kwargs: Any) -> list[MatchResult]:
        """执行匹配，返回结果列表。"""


class ResultFormatter:
    """统一结果格式化。"""

    @staticmethod
    def success(data: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "success",
            "data": data,
            "metadata": metadata,
        }

    @staticmethod
    def not_found(reason: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"status": "not_found", "error": reason}
        if metadata:
            result["metadata"] = metadata
        return result

    @staticmethod
    def error(message: str) -> dict[str, Any]:
        return {
            "status": "error",
            "error": message,
        }


class ContentFetcher:
    """从数据库获取文档内容，支持缓存。"""

    def __init__(self) -> None:
        self._cache: dict[int, dict[str, str]] = {}

    async def get(self, document_id: int) -> tuple[str, str] | None:
        """获取 (title, content)，支持缓存。"""
        if document_id in self._cache:
            cached = self._cache[document_id]
            return cached["title"], cached["content"]

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT title, content FROM articles WHERE id = $1",
                document_id,
            )
            if not row:
                return None

            title = self._get_field(row, "title")
            content = self._get_field(row, "content")
            self._cache[document_id] = {"title": title, "content": content}
            return title, content

    def clear_cache(self) -> None:
        """清空缓存。"""
        self._cache.clear()

    @staticmethod
    def _get_field(row: Any, key: str) -> str:
        """兼容 asyncpg Record 和测试中的对象 mock。"""
        value = getattr(row, key, None)
        if isinstance(value, str):
            return value
        try:
            return row[key]
        except Exception:
            attr = getattr(row, key)
            return attr if isinstance(attr, str) else str(attr)


class KeywordMatcher(Matcher):
    """关键词精确匹配。"""

    async def match(
        self,
        content: str,
        keyword: str,
        context_lines: int = 0,
        max_results: int = 3,
        **kwargs: Any,
    ) -> list[MatchResult]:
        if not keyword:
            return []

        paragraphs = [p for p in content.split("\n\n") if p.strip()]
        lines = content.split("\n")
        results: list[MatchResult] = []

        for paragraph in paragraphs:
            if keyword not in paragraph:
                continue

            line_number = self._find_line_number(lines, paragraph)
            before, after = self._extract_context(lines, line_number, context_lines)
            highlight_ranges = self._find_highlights(paragraph, keyword)

            results.append(
                MatchResult(
                    content=paragraph,
                    line_number=line_number,
                    context_before=before,
                    context_after=after,
                    highlight_ranges=highlight_ranges,
                )
            )
            if len(results) >= max_results:
                break

        return results

    @staticmethod
    def _find_highlights(paragraph: str, keyword: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = paragraph.find(keyword, start)
            if idx < 0:
                return ranges
            ranges.append((idx, idx + len(keyword)))
            start = idx + 1

    @staticmethod
    def _find_line_number(lines: list[str], paragraph: str) -> int:
        first_line = next((line for line in paragraph.split("\n") if line.strip()), "")
        if not first_line:
            return 1
        for i, line in enumerate(lines):
            if line.strip() == first_line.strip():
                return i + 1
        return 1

    @staticmethod
    def _extract_context(
        lines: list[str],
        line_number: int,
        context_lines: int,
    ) -> tuple[list[str], list[str]]:
        if context_lines <= 0:
            return [], []
        before: list[str] = []
        idx = line_number - 2
        while idx >= 0 and len(before) < context_lines:
            text = lines[idx].strip()
            if text:
                before.append(text)
            idx -= 1
        before.reverse()

        after: list[str] = []
        idx = line_number
        while idx < len(lines) and len(after) < context_lines:
            text = lines[idx].strip()
            if text:
                after.append(text)
            idx += 1

        return before, after


class RegexMatcher(Matcher):
    """正则表达式匹配。"""

    async def match(
        self,
        content: str,
        pattern: str,
        context_lines: int = 0,
        **kwargs: Any,
    ) -> list[MatchResult]:
        if not pattern:
            return []

        try:
            compiled = re.compile(pattern)
        except re.error:
            return []

        lines = content.split("\n")
        results: list[MatchResult] = []

        for match in compiled.finditer(content):
            line_number = content[:match.start()].count("\n") + 1
            before, after = KeywordMatcher._extract_context(lines, line_number, context_lines)
            matched = match.group(0)
            results.append(
                MatchResult(
                    content=matched,
                    line_number=line_number,
                    context_before=before,
                    context_after=after,
                    highlight_ranges=[(0, len(matched))],
                )
            )

        return results


class SectionMatcher(Matcher):
    """章节标题匹配。"""

    async def match(
        self,
        content: str,
        section: str,
        **kwargs: Any,
    ) -> list[MatchResult]:
        if not section:
            return []

        lines = content.split("\n")
        section_content: list[str] = []
        capturing = False
        line_number = 0

        for i, line in enumerate(lines):
            if section in line:
                capturing = True
                line_number = i + 1

            if capturing:
                section_content.append(line)
                if line.strip() and line[0] in "#一二三四五六七八九十" and section not in line:
                    break
                if len(section_content) > 100:
                    break

        if not section_content:
            return []

        return [
            MatchResult(
                content="\n".join(section_content),
                line_number=line_number,
                context_before=[],
                context_after=[],
                highlight_ranges=[],
            )
        ]


class LineRangeMatcher(Matcher):
    """精确行范围匹配。"""

    async def match(
        self,
        content: str,
        start_line: int,
        end_line: int | None = None,
        **kwargs: Any,
    ) -> list[MatchResult]:
        lines = content.split("\n")
        total_lines = len(lines)

        if start_line < 1 or start_line > total_lines:
            return []

        if end_line is None:
            end_line = total_lines
        else:
            end_line = min(end_line, total_lines)

        selected_lines = lines[start_line - 1 : end_line]
        return [
            MatchResult(
                content="\n".join(selected_lines),
                line_number=start_line,
                context_before=[],
                context_after=[],
                highlight_ranges=[],
            )
        ]