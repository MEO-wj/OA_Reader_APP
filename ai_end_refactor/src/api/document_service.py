"""文档服务 - 处理通用文档上传和导入

复用 import 脚本的核心逻辑，封装为可复用的异步函数。
"""
from __future__ import annotations

from typing import Any

import openai

from src.chat.prompts_runtime import (
    DOC_SUMMARY_SYSTEM_PROMPT,
    DOC_SUMMARY_USER_PROMPT_TEMPLATE,
)
from src.config.settings import Config
from src.core.db import get_pool
from src.core.base_retrieval import generate_embedding
from src.core.hash_utils import compute_document_hash


# ============================================================================
# 通用文档导入
# ============================================================================


async def generate_document_summary(title: str, content: str) -> str:
    """使用大模型生成文档的摘要介绍

    Args:
        title: 文档标题
        content: 文档完整内容

    Returns:
        生成的摘要文本
    """
    config = Config.load()
    async with openai.AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url
    ) as client:
        prompt = DOC_SUMMARY_USER_PROMPT_TEMPLATE.format(title=title, content=content)

        response = await client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": DOC_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )

        if not response.choices or not response.choices[0].message.content:
            raise ValueError("API 返回空响应")
        return response.choices[0].message.content.strip()


async def import_document_content(
    title: str,
    content: str,
    source_type: str = "markdown"
) -> dict[str, Any]:
    """导入通用文档内容到 documents 表

    Args:
        title: 文档标题
        content: 文档内容
        source_type: 文档类型 (markdown/json 等)

    Returns:
        导入结果字典
    """
    try:
        if not content.strip():
            return {"status": "error", "message": "内容为空"}

        # 使用大模型生成摘要
        summary = await generate_document_summary(title, content)

        # 计算内容哈希（JSON 走标准化）
        content_hash = compute_document_hash(content, source_type)

        # 生成 embedding
        embedding_list = await generate_embedding(summary)
        embedding_str = "[" + ",".join(str(x) for x in embedding_list) + "]"

        # 存入 documents 表
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO documents (title, content, summary, source_type, embedding, content_hash)
                VALUES ($1, $2, $3, $4, $5::vector, $6)
                ON CONFLICT (content_hash) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    summary = EXCLUDED.summary,
                    source_type = EXCLUDED.source_type,
                    embedding = EXCLUDED.embedding
                RETURNING id
            """, title, content, summary, source_type, embedding_str, content_hash)

        return {
            "status": "success",
            "message": "导入成功",
            "document": {
                "id": row["id"],
                "title": title,
                "type": source_type
            },
            "processing_steps": [
                "读取文件内容",
                f"生成摘要 ({len(summary)} 字符)",
                "生成向量 (1024维)",
                "存入数据库"
            ]
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================================
# 列表和删除（仅支持通用 documents 类型）
# ============================================================================


async def list_documents(
    document_type: str,
    limit: int = 100,
    offset: int = 0
) -> dict[str, Any]:
    """获取文档列表（仅支持 documents 类型）

    Args:
        document_type: 文档类型（仅支持 "documents"）
        limit: 返回数量
        offset: 偏移量

    Returns:
        文档列表字典
    """
    try:
        if document_type != "documents":
            return {
                "status": "error",
                "message": f"不支持的资料类型: {document_type}，仅支持 documents"
            }

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, title, source_type, summary, created_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
            """, limit, offset)
            total = await conn.fetchval("SELECT COUNT(*) FROM documents")

        return {
            "status": "success",
            "documents": [dict(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


async def delete_document(
    document_type: str,
    document_id: int
) -> dict[str, Any]:
    """删除文档（仅支持 documents 类型）

    Args:
        document_type: 文档类型（仅支持 "documents"）
        document_id: 文档 ID

    Returns:
        删除结果字典
    """
    try:
        if document_type != "documents":
            return {
                "status": "error",
                "message": f"不支持的资料类型: {document_type}，仅支持 documents"
            }

        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE id = $1",
                document_id
            )

            # 检查是否删除成功
            if "DELETE 0" in str(result):
                return {"status": "error", "message": f"未找到 ID 为 {document_id} 的文档"}

        return {
            "status": "success",
            "message": "删除成功",
            "document_id": document_id
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
