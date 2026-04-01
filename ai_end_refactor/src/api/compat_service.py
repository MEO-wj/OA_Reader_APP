"""兼容编排服务 - 将旧 JSON API 请求桥接到新 ChatClient 事件流。

CompatService 负责两件事：
1. ``ask``      — 聚合 ChatClient 事件流为单个 JSON 响应，兼容旧 /ask 接口
2. ``clear_memory`` — 创建新会话（不删除旧数据），兼容旧 /clear_memory 接口
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from src.config.settings import Config
from src.db.memory import MemoryDB

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _today_range() -> tuple[datetime, datetime]:
    """返回"今天"的 UTC 时间范围 [start, end)（naive datetime）。

    Returns:
        (start, end) — 均为 naive datetime，UTC+0。
    """
    now = datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def build_runtime_hints(
    top_k: Any = None,
    display_name: str | None = None,
) -> dict[str, str]:
    """根据旧 /ask 请求参数构建运行时提示。

    将 ``top_k`` 和 ``display_name`` 转换为可追加到用户问题末尾的提示文本。

    Args:
        top_k:        用户期望的返回条数。仅当为正整数（或可解析为正整数的字符串）时生效。
        display_name: 用户显示名称。非空时生成称呼提示。

    Returns:
        键为提示类别（``"top_k"`` / ``"display_name"``），值为提示文本的字典。
        无有效提示时返回空字典。
    """
    hints: dict[str, str] = {}

    # --- top_k 处理 ---
    parsed_top_k: int | None = None
    if isinstance(top_k, int) and not isinstance(top_k, bool):
        parsed_top_k = top_k
    elif isinstance(top_k, str):
        try:
            parsed_top_k = int(top_k)
        except (ValueError, TypeError):
            pass

    if parsed_top_k is not None and parsed_top_k > 0:
        hints["top_k"] = f"请优先返回前 {parsed_top_k} 条相关结果"

    # --- display_name 处理 ---
    if display_name:
        hints["display_name"] = f"可酌情称呼用户为{display_name}"

    return hints


# ---------------------------------------------------------------------------
# CompatService
# ---------------------------------------------------------------------------

class CompatService:
    """旧 AI End 兼容编排服务。"""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()

    # -- 依赖注入钩子（方便单测 monkeypatch） --

    def _create_memory_db(self) -> MemoryDB:
        """创建 MemoryDB 实例（可在测试中被替换）。"""
        return MemoryDB()

    async def _create_chat_client(
        self,
        config: Config,
        user_id: str | None,
        conversation_id: str | None,
    ):
        """创建 ChatClient 实例（可在测试中被替换）。"""
        from src.di.providers import create_chat_client
        return await create_chat_client(config, user_id, conversation_id)

    # -- 会话解析 --

    async def _resolve_session(
        self,
        user_id: str,
    ) -> tuple[str, bool]:
        """根据 user_id 解析/创建当天会话。

        Returns:
            (conversation_id, session_created)
        """
        db = self._create_memory_db()

        # 用 config 中的时区计算"今天"的 UTC 范围
        start_utc, end_utc = _today_range()

        session = await db.get_latest_session_in_utc_range(
            user_id, start_utc, end_utc,
        )

        if session:
            conversation_id = str(session["conversation_id"])
            return conversation_id, False

        # 无当天会话 → 创建新的
        new_id = uuid.uuid4().hex[:8]
        await db.create_session(user_id, new_id, "新会话")
        return new_id, True

    # -- 事件聚合 --

    @staticmethod
    def _truncate_text(text: str | None, limit: int = 80) -> str:
        """截断文本并压缩空白。

        Args:
            text:  待处理的文本，None 或空字符串返回空字符串。
            limit: 最大字符数，超出时截断并添加省略号。

        Returns:
            压缩空白后的文本，超长时以 "…" 结尾。
        """
        if not text:
            return ""
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[:limit].rstrip()}…"

    # -- 标准化与去重 --

    @staticmethod
    def _normalize_tool_result_to_docs(parsed: Any) -> list[dict]:
        """将 tool_result 解析后的数据统一标准化为文档列表。

        兼容三种输入结构：
          - list → 直接使用
          - dict 含 "results" 键 → 取 results 列表
          - 单个 dict → 包裹为单元素列表

        过滤非 dict 项，并为每篇文档补 summary_snippet。
        """
        docs: list[dict] = []
        if isinstance(parsed, list):
            docs = list(parsed)
        elif isinstance(parsed, dict):
            results = parsed.get("results")
            if isinstance(results, list):
                docs = list(results)
            else:
                docs = [parsed]
        else:
            return []

        # 过滤非 dict 项
        docs = [d for d in docs if isinstance(d, dict)]

        # 为每篇文档补 summary_snippet
        for doc in docs:
            doc["summary_snippet"] = CompatService._truncate_text(
                doc.get("summary"),
            )

        return docs

    @staticmethod
    def _dedupe_and_aggregate_docs(docs: list[dict]) -> list[dict]:
        """对文档列表按 id 去重并聚合评分字段。

        - 有 id 的文档：按 id 分组聚合
        - 无 id 的文档：直接透传（passthrough）
        - 评分字段（ebd_similarity, keyword_similarity, rerank_score）：分别计算非空平均值
        - 展示字段（title, unit, summary 等）：保留首个非空值
        """
        _SCORE_FIELDS = ("ebd_similarity", "keyword_similarity", "rerank_score")

        # 分离：有 id / 无 id
        with_id: dict[Any, list[dict]] = {}
        no_id: list[dict] = []

        for doc in docs:
            doc_id = doc.get("id")
            if doc_id is not None:
                with_id.setdefault(doc_id, []).append(doc)
            else:
                no_id.append(doc)

        aggregated: list[dict] = []

        for doc_id, group in with_id.items():
            merged: dict[str, Any] = {"id": doc_id}

            # 展示字段：保留首个非空值
            all_keys: set[str] = set()
            for d in group:
                all_keys.update(d.keys())
            display_keys = all_keys - {"id"} - set(_SCORE_FIELDS)

            for key in display_keys:
                # 优先取首个非空值（跳过 None 和空字符串）
                fallback: Any = None
                for d in group:
                    val = d.get(key)
                    if val is not None and val != "":
                        merged[key] = val
                        break
                    if fallback is None and key in d:
                        fallback = val
                else:
                    # 所有文档中该字段都为空，保留空值
                    if key not in merged:
                        merged[key] = fallback

            # 评分字段：仅接受 int/float（排除 bool/NaN）后求平均
            for field in _SCORE_FIELDS:
                values = [
                    d[field] for d in group
                    if isinstance(d.get(field), (int, float))
                    and not isinstance(d.get(field), bool)
                    and d[field] == d[field]  # NaN != NaN → 排除 NaN
                ]
                if values:
                    merged[field] = sum(values) / len(values)
                else:
                    merged[field] = None

            aggregated.append(merged)

        # 无 id 文档直接透传
        aggregated.extend(no_id)

        return aggregated

    @staticmethod
    def _aggregate_events(
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """将 ChatClient 事件列表聚合为单个 JSON 字典。

        事件类型：
          - ``delta``      → 拼接 content 到 answer
          - ``tool_result``→ 仅 tool 为 ``search_articles`` 时，解析 result 追加到 related_articles；其他 tool 跳过
          - ``done``       → 忽略（标记结束）
          - ``error``      → 记录错误信息
        """
        answer_parts: list[str] = []
        all_docs: list[dict] = []
        error_message: str | None = None

        for event in events:
            event_type = event.get("type", "")

            if event_type == "delta":
                content = event.get("content", "")
                if content:
                    answer_parts.append(content)

            elif event_type == "tool_result":
                # 只提取 search_articles 的结果，跳过其他 tool（如 grep_article）
                tool_name = event.get("tool", "")
                if tool_name != "search_articles":
                    continue
                raw_result = event.get("result", "")
                if isinstance(raw_result, str):
                    try:
                        parsed = json.loads(raw_result)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "Failed to parse tool_result as JSON: %s",
                            raw_result[:200],
                        )
                        parsed = None
                else:
                    parsed = raw_result

                if parsed is not None:
                    normalized = CompatService._normalize_tool_result_to_docs(parsed)
                    all_docs.extend(normalized)

            elif event_type == "error":
                msg = event.get("message", "")
                if msg:
                    error_message = msg

        # 去重聚合
        related_articles = CompatService._dedupe_and_aggregate_docs(all_docs)

        result: dict[str, Any] = {
            "answer": "".join(answer_parts),
            "related_articles": related_articles,
        }
        if error_message is not None:
            result["error"] = error_message

        return result

    # -- 公开接口 --

    async def ask(
        self,
        question: str,
        user_id: str | None = None,
        top_k: Any = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """兼容旧 /ask 接口：聚合事件流，返回单个 JSON。

        Args:
            question:     用户问题
            user_id:      用户 ID（可选）。为 None 时跳过会话管理。
            top_k:        用户期望的返回条数（可选）。
            display_name: 用户显示名称（可选）。

        Returns:
            至少包含 ``answer`` 和 ``related_articles`` 的字典。
            当 ``user_id`` 存在时，额外包含 ``conversation_id`` 和 ``session_created``。
        """
        conversation_id: str | None = None
        session_created: bool = False

        # 1) 构建运行时提示并追加到问题
        hints = build_runtime_hints(top_k=top_k, display_name=display_name)
        if hints:
            hint_text = "\n".join(hints.values())
            effective_question = f"{question}\n{hint_text}"
        else:
            effective_question = question

        # 2) 会话解析（仅 user_id 存在时）
        if user_id:
            conversation_id, session_created = await self._resolve_session(user_id)

        # 3) 创建 ChatClient 并收集事件
        client = await self._create_chat_client(
            self.config, user_id, conversation_id,
        )

        collected_events: list[dict[str, Any]] = []
        async for event in client.chat_stream_async(effective_question):
            collected_events.append(event)

        # 4) 聚合事件
        result = self._aggregate_events(collected_events)

        # 5) 附加会话字段（仅 user_id 存在时）
        if user_id:
            result["conversation_id"] = conversation_id
            result["session_created"] = session_created

        return result

    async def clear_memory(self, user_id: str | None = None) -> dict[str, Any]:
        """兼容旧 /clear_memory 接口：创建或复用当天会话。

        查询当天最新会话：
          1. 会话存在且有消息 → 创建新会话
          2. 会话存在但无消息 → 复用现有会话
          3. 无当天会话 → 创建新会话

        Args:
            user_id: 用户 ID（必须提供）。

        Returns:
            ``{"cleared": True, "conversation_id": "..."}``

        Raises:
            ValueError: user_id 为 None 时
        """
        if not user_id:
            raise ValueError("clear_memory requires a user_id")

        db = self._create_memory_db()
        start_utc, end_utc = _today_range()

        logger.info(
            "clear_memory debug: user_id=%s, range=[%s, %s)",
            user_id, start_utc.isoformat(), end_utc.isoformat(),
        )

        session = await db.get_latest_session_with_messages(
            user_id, start_utc, end_utc,
        )

        if session:
            messages = session.get("messages")
            # asyncpg 可能将 JSONB 返回为字符串，需要反序列化
            if isinstance(messages, str):
                messages = json.loads(messages)
            logger.info(
                "clear_memory debug: found session=%s, messages type=%s, len=%s",
                session.get("conversation_id"),
                type(messages).__name__,
                len(messages) if messages is not None else "N/A",
            )
            if messages:
                # 有消息 → 创建新会话
                new_id = uuid.uuid4().hex[:8]
                await db.create_session(user_id, new_id, "新会话")
                return {"cleared": True, "conversation_id": new_id}
            else:
                # 无消息 → 复用
                return {"cleared": True, "conversation_id": session["conversation_id"]}

        logger.info("clear_memory debug: no session found, creating new")
        # 无当天会话 → 创建新的
        new_id = uuid.uuid4().hex[:8]
        await db.create_session(user_id, new_id, "新会话")
        return {"cleared": True, "conversation_id": new_id}

    async def embed(self, text: str) -> list[float]:
        """兼容旧 /embed 接口：调用 generate_embedding 返回向量。

        Args:
            text: 需要生成向量的文本。

        Returns:
            浮点数向量列表。
        """
        from src.core.base_retrieval import generate_embedding

        return await generate_embedding(text)
