# src/db/memory.py
"""记忆系统数据库操作模块"""

import json
import uuid
from datetime import datetime
from typing import Any
from src.core.db import get_pool


class MemoryDB:
    """记忆系统数据库操作类"""

    async def ensure_user_exists(self, user_id: str) -> None:
        """确保用户记忆相关记录存在（幂等）。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_profiles (user_id, portrait_text, knowledge_text, updated_at)
                VALUES ($1, '', '', NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO conversations (user_id, conversation_id, title, messages, updated_at)
                VALUES ($1, 'default', '新会话', '[]'::jsonb, NOW())
                ON CONFLICT (user_id, conversation_id) DO NOTHING
                """,
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO conversation_sessions (user_id, conversation_id, title, updated_at)
                VALUES ($1, 'default', '新会话', NOW())
                ON CONFLICT (user_id, conversation_id) DO NOTHING
                """,
                user_id,
            )

    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """获取用户画像"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_profiles WHERE user_id = $1",
                user_id
            )
            if row:
                return dict(row)
            return None

    async def save_profile(
        self,
        user_id: str,
        portrait_text: str,
        knowledge_text: str
    ) -> None:
        """保存/更新用户画像"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_profiles (user_id, portrait_text, knowledge_text, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    portrait_text = EXCLUDED.portrait_text,
                    knowledge_text = EXCLUDED.knowledge_text,
                    updated_at = NOW()
                """,
                user_id, portrait_text, knowledge_text
            )

    async def create_session(
        self,
        user_id: str,
        conversation_id: str,
        title: str = "新会话",
    ) -> None:
        """创建新会话。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_sessions (user_id, conversation_id, title, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                ON CONFLICT (user_id, conversation_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    updated_at = NOW()
                """,
                user_id,
                conversation_id,
                title,
            )
            await conn.execute(
                """
                INSERT INTO conversations (user_id, conversation_id, title, messages, updated_at)
                VALUES ($1, $2, $3, '[]'::jsonb, NOW())
                ON CONFLICT (user_id, conversation_id) DO NOTHING
                """,
                user_id,
                conversation_id,
                title,
            )

    async def get_session(
        self,
        user_id: str,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        """获取会话信息。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, conversation_id, title, created_at, updated_at
                FROM conversation_sessions
                WHERE user_id = $1 AND conversation_id = $2
                """,
                user_id,
                conversation_id,
            )
            return dict(row) if row else None

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户所有会话。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, conversation_id, title, created_at, updated_at
                FROM conversation_sessions
                WHERE user_id = $1
                ORDER BY updated_at DESC
                """,
                user_id,
            )
            return [dict(row) for row in rows]

    async def get_latest_session_in_utc_range(
        self,
        user_id: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, Any] | None:
        """查询指定用户在给定 UTC 时间范围内最新创建的会话。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, conversation_id, title, created_at, updated_at
                FROM conversation_sessions
                WHERE user_id = $1
                  AND COALESCE(created_at, updated_at) >= $2
                  AND COALESCE(created_at, updated_at) < $3
                ORDER BY COALESCE(created_at, updated_at) DESC
                LIMIT 1
                """,
                user_id,
                start_utc,
                end_utc,
            )
            return dict(row) if row else None

    async def get_latest_session_with_messages(
        self,
        user_id: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, Any] | None:
        """查询当天最新会话及其消息状态。

        LEFT JOIN conversations 表获取 messages 字段，
        用于判断会话是否有消息（clear_memory 空会话复用）。
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT cs.user_id, cs.conversation_id, cs.title,
                       cs.created_at, cs.updated_at,
                       COALESCE(c.messages, '[]'::jsonb) AS messages
                FROM conversation_sessions cs
                LEFT JOIN conversations c
                    ON c.user_id = cs.user_id AND c.conversation_id = cs.conversation_id
                WHERE cs.user_id = $1
                  AND COALESCE(cs.created_at, cs.updated_at) >= $2
                  AND COALESCE(cs.created_at, cs.updated_at) < $3
                ORDER BY COALESCE(cs.created_at, cs.updated_at) DESC
                LIMIT 1
                """,
                user_id,
                start_utc,
                end_utc,
            )
            return dict(row) if row else None

    async def update_session_title(
        self,
        user_id: str,
        conversation_id: str,
        title: str,
    ) -> None:
        """更新会话标题。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE conversation_sessions
                SET title = $3, updated_at = NOW()
                WHERE user_id = $1 AND conversation_id = $2
                """,
                user_id,
                conversation_id,
                title,
            )
            await conn.execute(
                """
                UPDATE conversations
                SET title = $3, updated_at = NOW()
                WHERE user_id = $1 AND conversation_id = $2
                """,
                user_id,
                conversation_id,
                title,
            )

    async def delete_session(self, user_id: str, conversation_id: str) -> None:
        """删除指定会话。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM conversations WHERE user_id = $1 AND conversation_id = $2",
                user_id,
                conversation_id,
            )
            await conn.execute(
                "DELETE FROM conversation_sessions WHERE user_id = $1 AND conversation_id = $2",
                user_id,
                conversation_id,
            )

    async def get_or_create_session(
        self,
        user_id: str,
        conversation_id: str | None = None,
    ) -> tuple[str, str]:
        """获取或创建会话，返回 (conversation_id, title)。"""
        target_id = conversation_id or str(uuid.uuid4())[:8]
        session = await self.get_session(user_id, target_id)
        if session:
            return target_id, str(session.get("title") or "新会话")

        await self.create_session(user_id, target_id, "新会话")
        return target_id, "新会话"

    async def get_conversation(
        self,
        user_id: str,
        conversation_id: str = "default",
    ) -> list[dict[str, Any]]:
        """获取对话历史"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT messages
                FROM conversations
                WHERE user_id = $1 AND conversation_id = $2
                """,
                user_id,
                conversation_id,
            )
            if row:
                messages = row["messages"]
                if isinstance(messages, str):
                    return json.loads(messages)
                return messages
            return []

    async def save_conversation(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        conversation_id: str = "default",
    ) -> None:
        """保存/更新对话历史"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (user_id, conversation_id, title, messages, updated_at)
                VALUES ($1, $2, '新会话', $3::jsonb, NOW())
                ON CONFLICT (user_id, conversation_id) DO UPDATE SET
                    messages = EXCLUDED.messages,
                    updated_at = NOW()
                """,
                user_id,
                conversation_id,
                json.dumps(messages, ensure_ascii=False),
            )
            await conn.execute(
                """
                INSERT INTO conversation_sessions (user_id, conversation_id, title, created_at, updated_at)
                VALUES ($1, $2, '新会话', NOW(), NOW())
                ON CONFLICT (user_id, conversation_id) DO UPDATE SET
                    updated_at = NOW()
                """,
                user_id,
                conversation_id,
            )

    async def append_conversation(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        conversation_id: str = "default",
    ) -> None:
        """原子追加对话历史，避免并发读改写覆盖。"""
        if not messages:
            return

        pool = await get_pool()
        payload = json.dumps(messages, ensure_ascii=False)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (user_id, conversation_id, title, messages, updated_at)
                VALUES ($1, $2, '新会话', $3::jsonb, NOW())
                ON CONFLICT (user_id, conversation_id) DO UPDATE SET
                    messages = COALESCE(conversations.messages, '[]'::jsonb) || EXCLUDED.messages,
                    updated_at = NOW()
                """,
                user_id,
                conversation_id,
                payload,
            )
            await conn.execute(
                """
                INSERT INTO conversation_sessions (user_id, conversation_id, title, updated_at)
                VALUES ($1, $2, '新会话', NOW())
                ON CONFLICT (user_id, conversation_id) DO UPDATE SET
                    updated_at = NOW()
                """,
                user_id,
                conversation_id,
            )

    async def replace_conversation(
        self,
        user_id: str,
        messages: list[dict[str, Any]],
        conversation_id: str = "default",
    ) -> None:
        """替换对话历史（用于压缩后保存）。"""
        pool = await get_pool()
        payload = json.dumps(messages, ensure_ascii=False)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (user_id, conversation_id, title, messages, updated_at)
                VALUES ($1, $2, '新会话', $3::jsonb, NOW())
                ON CONFLICT (user_id, conversation_id) DO UPDATE SET
                    messages = EXCLUDED.messages,
                    updated_at = NOW()
                """,
                user_id,
                conversation_id,
                payload,
            )

    async def list_recent_users(self, limit: int = 20) -> list[dict[str, Any]]:
        """列出最近有对话的用户。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, MAX(updated_at) AS updated_at
                FROM conversations
                GROUP BY user_id
                ORDER BY MAX(updated_at) DESC
                LIMIT $1
                """,
                limit,
            )
            return [dict(row) for row in rows]

    async def clear_user_memory(self, user_id: str) -> None:
        """清空用户画像和对话历史。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM user_profiles
                WHERE user_id = $1
                """,
                user_id,
            )
            await conn.execute(
                """
                DELETE FROM conversations
                WHERE user_id = $1
                """,
                user_id,
            )

    async def get_db_timezone(self) -> str | None:
        """查询 PostgreSQL 会话时区名称。"""
        pool = await get_pool()
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow("SHOW TIMEZONE")
                if row:
                    return str(row["TimeZone"] if "TimeZone" in row else row[0])
        except Exception:
            return None
        return None
