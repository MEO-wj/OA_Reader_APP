"""文档检索模块

提供文档的向量搜索功能。
"""
import asyncio
import re
from typing import Any

from src.config.settings import Config
from src.core.api_clients import get_embedding_client, get_rerank_client, close_clients
from src.core.api_queue import get_api_queue
from src.core.base_retrieval import BaseRetriever
from src.core.db import get_pool
from src.core.document_content import (
    ContentFetcher,
    KeywordMatcher,
    LineRangeMatcher,
    Matcher,
    RegexMatcher,
    ResultFormatter,
    SectionMatcher,
)


def _is_transient_db_error(error: Exception) -> bool:
    message = str(error).lower()
    markers = (
        "connection was closed",
        "another operation is in progress",
        "connection is closed",
    )
    return any(marker in message for marker in markers)


def _get_embedding_client():
    """兼容旧测试与调用路径。"""
    return get_embedding_client()


def _get_rerank_client():
    """获取 Rerank 客户端。"""
    return get_rerank_client()


def _parse_id_list_from_content(content: str) -> list[int]:
    """从字符串内容中解析数字 ID 列表。

    当 API 返回非标准格式时，从 LLM 响应文本中提取 ID。

    Args:
        content: 包含数字 ID 的字符串内容

    Returns:
        解析出的 ID 列表
    """
    import re
    numbers = re.findall(r"\d+", content)
    return [int(n) for n in numbers]


def _generate_embedding_sync(text: str) -> list[float]:
    """同步生成文本的向量表示

    Args:
        text: 要向量化的文本

    Returns:
        向量表示（维度由配置决定）
    """
    if not text or not text.strip():
        raise ValueError("文本不能为空")

    config = Config.load()
    client = _get_embedding_client()

    response = client.embeddings.create(
        model=config.embedding_model,
        input=text,
        dimensions=config.embedding_dimensions
    )

    return response.data[0].embedding


async def generate_embedding(text: str) -> list[float]:
    """异步生成文本的向量表示（在线程池中执行同步版本）

    Args:
        text: 要向量化的文本

    Returns:
        向量表示（维度由配置决定）
    """
    return await get_api_queue().submit("embedding", _generate_embedding_sync, text)


def _rerank_documents_sync(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int | None = None
) -> list[dict[str, Any]]:
    """同步调用 Rerank API 对候选文档重新排序

    Args:
        query: 用户查询文本
        candidates: 候选文档列表，每个文档包含 id/title/summary 等字段
        top_k: 返回的文档数量上限，默认为 len(candidates)

    Returns:
        按 rerank 分数排序后的文档列表

    Raises:
        RuntimeError: 当 rerank API 调用失败时
    """
    if not candidates:
        return []

    if top_k is None:
        top_k = len(candidates)

    config = Config.load()
    client = _get_rerank_client()

    # 构建文档文本列表（使用 title + summary 作为 rerank 输入）
    documents = []
    for doc in candidates:
        text_parts = []
        if "title" in doc and doc["title"]:
            text_parts.append(doc["title"])
        if "summary" in doc and doc["summary"]:
            text_parts.append(doc["summary"])
        documents.append("\n".join(text_parts) if text_parts else str(doc.get("id", "")))

    # 调用 rerank API
    # 使用标准 OpenAI API 格式：responses.create
    try:
        response = client.responses.create(
            model=config.rerank_model,
            query=query,
            documents=documents,
            top_k=top_k
        )

        # 构建索引映射
        id_map = {i: doc for i, doc in enumerate(candidates)}
        results = []

        # 标准格式解析：根据 one-api 的响应格式调整解析逻辑
        if hasattr(response, "results") and response.results:
            for item in sorted(response.results, key=lambda x: x.relevance_score, reverse=True):
                idx = item.index
                if idx in id_map:
                    doc = id_map[idx].copy()
                    doc["rerank_score"] = item.relevance_score
                    results.append(doc)
        else:
            # Fallback 分支：当 API 返回非标准格式时，尝试从 LLM 响应中解析 ID 列表
            # 将响应转换为字符串并解析数字 ID
            response_text = str(response)
            parsed_ids = _parse_id_list_from_content(response_text)

            if parsed_ids:
                # 按 ID 在候选列表中的顺序排序
                for doc_id in parsed_ids:
                    # 在 candidates 中查找匹配的文档
                    for doc in candidates:
                        if doc.get("id") == doc_id:
                            doc_copy = doc.copy()
                            if doc_copy not in results:
                                results.append(doc_copy)
                            break

        # 如果解析结果为空，返回原始候选列表
        if not results:
            return candidates

        return results

    except Exception as e:
        raise RuntimeError(f"Rerank API 调用失败: {str(e)}") from e


async def _rerank_documents(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int | None = None
) -> list[dict[str, Any]]:
    """异步调用 Rerank API 对候选文档重新排序

    Args:
        query: 用户查询文本
        candidates: 候选文档列表
        top_k: 返回的文档数量上限，默认为 len(candidates)

    Returns:
        按 rerank 分数排序后的文档列表
        失败时降级返回原始候选列表
    """
    if not candidates:
        return []

    try:
        return await get_api_queue().submit("rerank", _rerank_documents_sync, query, candidates, top_k)
    except Exception:
        # Rerank 失败时降级返回原始列表
        return candidates


def _merge_results(
    ebd_results: dict[int, dict[str, Any]],
    keyword_results: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """合并 EBD 和关键词搜索结果

    Args:
        ebd_results: EBD 搜索结果 {doc_id: result}
        keyword_results: 关键词搜索结果 {doc_id: result}

    Returns:
        合并后的候选文档列表（去重）
    """
    all_docs: dict[int, dict[str, Any]] = {}

    # 添加 EBD 结果
    for doc_id, result in ebd_results.items():
        all_docs[doc_id] = result.copy()

    # 添加/合并关键词结果
    for doc_id, kw_result in keyword_results.items():
        if doc_id in all_docs:
            # 同一文档在两层都出现：整合评分
            all_docs[doc_id]["keyword_similarity"] = kw_result["keyword_similarity"]
        else:
            # 只在关键词层出现
            all_docs[doc_id] = kw_result

    return list(all_docs.values())


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    """兼容 asyncpg.Record 与测试中的 mock 行对象取值。"""
    try:
        return row[key]
    except Exception:
        return getattr(row, key, default)


async def _search_by_keywords(
    keywords: str,
    pool,
    limit: int = 20
) -> list[dict[str, Any]]:
    """使用 pg_trgm 进行关键词模糊搜索

    Args:
        keywords: 逗号分隔的关键词字符串
        pool: 数据库连接池
        limit: 返回结果数量上限

    Returns:
        匹配文档列表
    """
    # 解析关键词
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        return []

    results = []
    async with pool.acquire() as conn:
        # 对每个关键词进行搜索
        for keyword in keyword_list:
            # 使用 pg_trgm 的相似度函数
            # 搜索 content 和 title
            rows = await conn.fetch("""
                SELECT id, title, summary, created_at,
                       GREATEST(
                           similarity(title, $2),
                           similarity(content, $2)
                       ) as similarity
                FROM documents
                WHERE title % $2 OR content % $2
                ORDER BY similarity DESC
                LIMIT $1
            """, limit, keyword)

            for row in rows:
                # 记录关键词来源（用于调试）
                results.append({
                    "id": row["id"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "created_at": row["created_at"],
                    "keyword_similarity": float(row["similarity"]),
                    "matched_keyword": keyword
                })

    return results


class DocumentRetriever(BaseRetriever):
    """文档检索器。"""

    def __init__(self):
        super().__init__(
            table_name="documents",
            select_columns=["id", "title", "summary", "created_at"],
            embedding_column="embedding",
            get_pool_fn=get_pool,
            rerank_fn=_rerank_documents,
            is_transient_error=_is_transient_db_error,
        )

    async def _build_metadata_filter(
        self,
        start_index: int = 1,
        **filters: Any,
    ) -> tuple[str, list[Any]]:
        # 当前 documents 表无元数据过滤条件
        return "", []

    async def search_documents(
        self,
        query: str,
        keywords: str | None = None,
        top_k: int = 10,
        threshold: float = 0.5,
    ) -> dict[str, Any]:
        """三层检索策略搜索相关文档。"""
        if not query or not query.strip():
            raise ValueError("查询文本不能为空")

        try:
            query_embedding = await generate_embedding(query)
            query_embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        except Exception as exc:
            return {"error": f"搜索失败: {str(exc)}", "results": []}

        try:
            ebd_rows = await self._vector_search(
                query_embedding_str=query_embedding_str,
                limit=20,
                threshold=threshold,
            )
        except RuntimeError as exc:
            if str(exc) == "TRANSIENT_DB_ERROR":
                return {"error": "搜索失败: 临时数据库连接异常，请稍后重试", "results": []}
            return {"error": f"搜索失败: {str(exc)}", "results": []}
        except Exception as exc:
            return {"error": f"搜索失败: {str(exc)}", "results": []}

        ebd_results: dict[int, dict[str, Any]] = {}
        for row in ebd_rows:
            row_id = _row_value(row, "id")
            ebd_results[row_id] = {
                "id": row_id,
                "title": _row_value(row, "title"),
                "summary": _row_value(row, "summary"),
                "created_at": _row_value(row, "created_at"),
                "ebd_similarity": float(_row_value(row, "similarity", 0.0)),
                "keyword_similarity": None,
            }

        keyword_results: dict[int, dict[str, Any]] = {}
        if keywords:
            try:
                pool = await get_pool()
                kw_rows = await _search_by_keywords(keywords, pool, limit=20)
                for row in kw_rows:
                    doc_id = row["id"]
                    if doc_id in keyword_results:
                        if row["keyword_similarity"] > keyword_results[doc_id]["keyword_similarity"]:
                            keyword_results[doc_id]["keyword_similarity"] = row["keyword_similarity"]
                    else:
                        keyword_results[doc_id] = {
                            "id": row["id"],
                            "title": row["title"],
                            "summary": row["summary"],
                            "created_at": row["created_at"],
                            "ebd_similarity": None,
                            "keyword_similarity": row["keyword_similarity"],
                        }
            except Exception:
                pass

        candidates = _merge_results(ebd_results, keyword_results)
        reranked_results = await self._rerank(query, candidates, top_k)

        formatted_results = []
        for doc in reranked_results[:top_k]:
            formatted_results.append({
                "id": doc["id"],
                "title": doc["title"],
                "summary": doc["summary"],
                "ebd_similarity": doc.get("ebd_similarity"),
                "keyword_similarity": doc.get("keyword_similarity"),
                "rerank_score": doc.get("rerank_score"),
            })
        return {"results": formatted_results}


async def search_documents(
    query: str,
    keywords: str | None = None,
    top_k: int = 10,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """兼容旧接口：转发到 DocumentRetriever。"""
    retriever = DocumentRetriever()
    return await retriever.search_documents(
        query=query,
        keywords=keywords,
        top_k=top_k,
        threshold=threshold,
    )


def _detect_mode(
    keyword: str | None,
    section: str | None,
    pattern: str | None,
    start_line: int | None,
) -> str:
    if pattern:
        return "regex"
    if start_line is not None:
        return "line_range"
    if section:
        return "section"
    if keyword:
        return "keyword"
    return "summary"


def _get_matcher(mode: str) -> Matcher:
    matchers: dict[str, Matcher] = {
        "keyword": KeywordMatcher(),
        "regex": RegexMatcher(),
        "section": SectionMatcher(),
        "line_range": LineRangeMatcher(),
    }
    if mode not in matchers:
        raise ValueError(f"Unknown mode: {mode}")
    return matchers[mode]


def _split_keyword_terms(keyword: str | None) -> list[str]:
    """将 keyword 按常见分隔符拆分为多个词项。"""
    if not keyword:
        return []
    parts = re.split(r"[,\uFF0C|]", keyword)
    terms = [part.strip() for part in parts if part and part.strip()]
    if not terms:
        return []
    # 去重并保持顺序
    return list(dict.fromkeys(terms))


async def _match_keyword_or(
    content: str,
    terms: list[str],
    context_lines: int,
    max_results: int,
) -> list[Any]:
    """多关键词 OR 匹配。"""
    matcher = KeywordMatcher()
    merged = []
    seen: set[tuple[int, str]] = set()

    for term in terms:
        partial = await matcher.match(
            content,
            keyword=term,
            context_lines=context_lines,
            max_results=max_results,
        )
        for item in partial:
            key = (item.line_number, item.content)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= max_results:
                return merged
    return merged


async def grep_document(
    document_id: int,
    keyword: str | None = None,
    section: str | None = None,
    mode: str = "auto",
    context_lines: int = 0,
    max_results: int = 3,
    pattern: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """获取指定文档的具体内容（增强版）。"""
    try:
        fetcher = ContentFetcher()
        fetched = await fetcher.get(document_id)
        if fetched is None:
            return ResultFormatter.not_found(f"文档 {document_id} 不存在")
        title, content = fetched

        current_mode = _detect_mode(keyword, section, pattern, start_line) if mode == "auto" else mode
        if current_mode == "summary":
            summary = content[:500] + "..." if len(content) > 500 else content
            return ResultFormatter.success(
                data={
                    "title": title,
                    "matches": [
                        {
                            "content": summary,
                            "line_number": 1,
                            "context_before": [],
                            "context_after": [],
                            "highlight_ranges": [],
                        }
                    ],
                },
                metadata={"total_matches": 1, "search_mode": "summary"},
            )

        try:
            matcher = _get_matcher(current_mode)
        except ValueError as exc:
            return ResultFormatter.error(str(exc))

        kwargs: dict[str, Any] = {"context_lines": context_lines}
        effective_mode = current_mode
        if current_mode == "keyword":
            terms = _split_keyword_terms(keyword)
            if len(terms) > 1:
                matches = await _match_keyword_or(content, terms, context_lines, max_results)
                effective_mode = "keyword_or"
                if not matches:
                    pattern_for_fallback = "|".join(re.escape(term) for term in terms)
                    regex_matcher = RegexMatcher()
                    matches = await regex_matcher.match(
                        content,
                        pattern=pattern_for_fallback,
                        context_lines=context_lines,
                    )
                    matches = matches[:max_results]
                    if matches:
                        effective_mode = "keyword_or_regex_fallback"
            else:
                kwargs["keyword"] = terms[0] if terms else keyword
                kwargs["max_results"] = max_results
                matcher = _get_matcher(current_mode)
                matches = await matcher.match(content, **kwargs)
        elif current_mode == "regex":
            kwargs["pattern"] = pattern
            matcher = _get_matcher(current_mode)
            matches = await matcher.match(content, **kwargs)
        elif current_mode == "section":
            kwargs["section"] = section
            matcher = _get_matcher(current_mode)
            matches = await matcher.match(content, **kwargs)
        elif current_mode == "line_range":
            kwargs["start_line"] = start_line
            kwargs["end_line"] = end_line
            matcher = _get_matcher(current_mode)
            matches = await matcher.match(content, **kwargs)
        else:
            matcher = _get_matcher(current_mode)
            matches = await matcher.match(content, **kwargs)
        if not matches:
            if current_mode == "keyword":
                return ResultFormatter.not_found(
                    f"未找到关键词 '{keyword}'",
                    metadata={"search_mode": effective_mode},
                )
            if current_mode == "section":
                return ResultFormatter.not_found(
                    f"未找到章节 '{section}'",
                    metadata={"search_mode": current_mode},
                )
            return ResultFormatter.not_found(
                "未找到匹配内容",
                metadata={"search_mode": current_mode},
            )

        formatted_matches = [
            {
                "content": item.content,
                "line_number": item.line_number,
                "context_before": item.context_before,
                "context_after": item.context_after,
                "highlight_ranges": item.highlight_ranges,
            }
            for item in matches
        ]
        return ResultFormatter.success(
            data={"title": title, "matches": formatted_matches},
            metadata={"total_matches": len(formatted_matches), "search_mode": effective_mode},
        )
    except Exception as exc:
        return ResultFormatter.error(f"获取文档失败: {str(exc)}")


async def grep_documents(
    document_ids: list[int],
    keyword: str | None = None,
    section: str | None = None,
    mode: str = "auto",
    context_lines: int = 0,
    max_results: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """跨多个文档搜索。"""
    results: list[dict[str, Any]] = []
    documents_with_matches = 0

    for document_id in document_ids:
        single = await grep_document(
            document_id=document_id,
            keyword=keyword,
            section=section,
            mode=mode,
            context_lines=context_lines,
            max_results=max_results,
            **kwargs,
        )
        if single.get("status") == "success":
            documents_with_matches += 1
            data = single.get("data", {})
            results.append(
                {
                    "document_id": document_id,
                    "title": data.get("title"),
                    "matches": data.get("matches", []),
                }
            )

    return ResultFormatter.success(
        data={"results": results},
        metadata={
            "total_documents": len(document_ids),
            "documents_with_matches": documents_with_matches,
            "search_mode": mode,
        },
    )


async def close_resources():
    """关闭检索模块的资源（embedding 客户端）"""
    await asyncio.get_event_loop().run_in_executor(None, close_clients)