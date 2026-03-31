"""文章检索模块

提供 OA 文章的向量搜索、关键词搜索和内容定位功能。
"""

from __future__ import annotations

import re
import logging
from typing import Any

from openai import BaseModel

from src.config.settings import Config
from src.core.api_clients import get_embedding_client, get_rerank_client
from src.core.api_queue import get_api_queue
from src.core.base_retrieval import BaseRetriever, generate_embedding

logger = logging.getLogger(__name__)
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
    return get_embedding_client()


def _get_rerank_client():
    return get_rerank_client()


class _RerankResult(BaseModel):
    index: int
    relevance_score: float


class _RerankResponse(BaseModel):
    results: list[_RerankResult] = []


def _parse_id_list_from_content(content: str) -> list[int]:
    """从字符串内容中解析数字 ID 列表。"""
    numbers = re.findall(r"\d+", content)
    return [int(n) for n in numbers]


def _rerank_documents_sync(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    """同步调用 Rerank API 对候选文章重新排序。"""
    if not candidates:
        return []
    if top_k is None:
        top_k = len(candidates)

    config = Config.load()
    client = _get_rerank_client()

    documents = []
    for doc in candidates:
        text_parts = []
        if "title" in doc and doc["title"]:
            text_parts.append(doc["title"])
        if "summary" in doc and doc["summary"]:
            text_parts.append(doc["summary"])
        documents.append("\n".join(text_parts) if text_parts else str(doc.get("id", "")))

    try:
        response = client.post(
            "/rerank",
            cast_to=_RerankResponse,
            body={
                "model": config.rerank_model,
                "query": query,
                "documents": documents,
                "top_n": top_k,
            },
        )

        id_map = {i: doc for i, doc in enumerate(candidates)}
        results = []

        if response.results:
            for item in sorted(response.results, key=lambda x: x.relevance_score, reverse=True):
                idx = item.index
                if idx in id_map:
                    doc = id_map[idx].copy()
                    doc["rerank_score"] = item.relevance_score
                    results.append(doc)
        else:
            response_text = str(response)
            parsed_ids = _parse_id_list_from_content(response_text)
            if parsed_ids:
                for doc_id in parsed_ids:
                    for doc in candidates:
                        if doc.get("id") == doc_id:
                            doc_copy = doc.copy()
                            if doc_copy not in results:
                                results.append(doc_copy)
                            break

        if not results:
            return candidates
        return results
    except Exception as e:
        raise RuntimeError(f"Rerank API 调用失败: {str(e)}") from e


async def _rerank_documents(
    query: str,
    candidates: list[dict[str, Any]],
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    try:
        return await get_api_queue().submit("rerank", _rerank_documents_sync, query, candidates, top_k)
    except Exception as e:
        logger.warning("Rerank failed, returning candidates as-is: %s", e)
        return candidates


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    """兼容 asyncpg.Record 与测试中的 mock 行对象取值。"""
    try:
        return row[key]
    except Exception:
        return getattr(row, key, default)


class ArticleRetriever(BaseRetriever):
    """OA 文章检索器，使用 vectors + articles JOIN 查询。"""

    def __init__(self):
        super().__init__(
            table_name="vectors",
            select_columns=["v.id", "a.title", "a.unit", "a.published_on", "a.summary"],
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
        return "", []

    async def _vector_search(
        self,
        query_embedding_str: str,
        limit: int = 20,
        threshold: float = 0.5,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """覆写基类：使用 JOIN 查询 vectors + articles。"""
        import asyncio

        params: list[Any] = [query_embedding_str, threshold]
        where_clauses = [
            "v.embedding IS NOT NULL",
            f"1 - (v.embedding <=> $1::vector) >= $2",
        ]

        if metadata_filters:
            filter_clause, filter_params = await self._build_metadata_filter(
                start_index=3, **metadata_filters,
            )
            if filter_clause:
                where_clauses.append(f"({filter_clause})")
                params.extend(filter_params)

        params.append(limit)
        limit_idx = len(params)

        sql = f"""
            SELECT v.id, a.title, a.unit, a.published_on, a.summary,
                   LEFT(a.content, 80) as content_snippet,
                   1 - (v.embedding <=> $1::vector) as similarity
            FROM vectors v
            JOIN articles a ON v.article_id = a.id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY v.embedding <=> $1::vector
            LIMIT ${limit_idx}
        """

        last_error: Exception | None = None
        for attempt in range(self._retry_attempts):
            try:
                pool = await self._get_pool_fn()
                async with pool.acquire() as conn:
                    rows = await conn.fetch(sql, *params)
                return list(rows)
            except Exception as exc:
                last_error = exc
                transient = self._is_transient_error(exc) if self._is_transient_error else False
                if transient and attempt < self._retry_attempts - 1:
                    await asyncio.sleep(self._retry_backoff)
                    continue
                break

        if last_error is not None and self._is_transient_error and self._is_transient_error(last_error):
            raise RuntimeError("TRANSIENT_DB_ERROR") from last_error
        if last_error is not None:
            raise last_error
        return []

    async def search_articles(
        self,
        query: str,
        keywords: str | None = None,
        top_k: int = 10,
        threshold: float = 0.5,
    ) -> dict[str, Any]:
        """三层检索策略搜索相关文章。"""
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
                "unit": _row_value(row, "unit"),
                "published_on": str(_row_value(row, "published_on", "")),
                "summary": _row_value(row, "summary"),
                "content_snippet": _row_value(row, "content_snippet"),
                "ebd_similarity": float(_row_value(row, "similarity", 0.0)),
                "keyword_similarity": None,
            }

        keyword_results: dict[int, dict[str, Any]] = {}
        if keywords:
            logger.info("search_articles keywords: %s", keywords)
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
                            "unit": row.get("unit"),
                            "published_on": str(row.get("published_on", "")),
                            "summary": row["summary"],
                            "content_snippet": row.get("content_snippet"),
                            "ebd_similarity": None,
                            "keyword_similarity": row["keyword_similarity"],
                        }
            except Exception:
                logger.warning("Layer 2 keyword search failed: %s", keywords)
        else:
            logger.info("search_articles keywords: (empty, Layer 2 skipped)")

        candidates = _merge_results(ebd_results, keyword_results)
        reranked_results = await self._rerank(query, candidates, top_k)

        formatted_results = []
        for doc in reranked_results[:top_k]:
            formatted_results.append({
                "id": doc["id"],
                "title": doc["title"],
                "unit": doc.get("unit"),
                "published_on": doc.get("published_on"),
                "summary": doc["summary"],
                "content_snippet": doc.get("content_snippet"),
                "ebd_similarity": doc.get("ebd_similarity"),
                "keyword_similarity": doc.get("keyword_similarity"),
                "rerank_score": doc.get("rerank_score"),
            })
        return {"results": formatted_results}


async def _search_by_keywords(
    keywords: str,
    pool,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """使用 pg_trgm 进行关键词模糊搜索（查 articles 表）。"""
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        return []

    results = []
    async with pool.acquire() as conn:
        for keyword in keyword_list:
            rows = await conn.fetch("""
                SELECT id, title, unit, published_on, summary,
                       LEFT(content, 80) as content_snippet,
                       GREATEST(
                           similarity(title, $2),
                           similarity(content, $2)
                       ) as similarity
                FROM articles
                WHERE title % $2 OR content % $2
                ORDER BY similarity DESC
                LIMIT $1
            """, limit, keyword)

            for row in rows:
                results.append({
                    "id": row["id"],
                    "title": row["title"],
                    "unit": row.get("unit"),
                    "published_on": str(row.get("published_on", "")),
                    "summary": row["summary"],
                    "content_snippet": row["content_snippet"],
                    "keyword_similarity": float(row["similarity"]),
                    "matched_keyword": keyword,
                })

    return results


def _merge_results(
    ebd_results: dict[int, dict[str, Any]],
    keyword_results: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    all_docs: dict[int, dict[str, Any]] = {}
    for doc_id, result in ebd_results.items():
        all_docs[doc_id] = result.copy()
    for doc_id, kw_result in keyword_results.items():
        if doc_id in all_docs:
            all_docs[doc_id]["keyword_similarity"] = kw_result["keyword_similarity"]
        else:
            all_docs[doc_id] = kw_result
    return list(all_docs.values())


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
    if not keyword:
        return []
    parts = re.split(r"[,\uFF0C|]", keyword)
    terms = [part.strip() for part in parts if part and part.strip()]
    if not terms:
        return []
    return list(dict.fromkeys(terms))


async def _match_keyword_or(
    content: str,
    terms: list[str],
    context_lines: int,
    max_results: int,
) -> list[Any]:
    matcher = KeywordMatcher()
    merged = []
    seen: set[tuple[int, str]] = set()
    for term in terms:
        partial = await matcher.match(
            content, keyword=term, context_lines=context_lines, max_results=max_results,
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


async def grep_article(
    article_id: int,
    keyword: str | None = None,
    section: str | None = None,
    mode: str = "auto",
    context_lines: int = 0,
    max_results: int = 3,
    pattern: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """获取指定文章的具体内容。"""
    try:
        fetcher = ContentFetcher()
        fetched = await fetcher.get(article_id)
        if fetched is None:
            return ResultFormatter.not_found(f"文章 {article_id} 不存在")
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
                        content, pattern=pattern_for_fallback, context_lines=context_lines,
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
            matches = await matcher.match(content, **kwargs)
        elif current_mode == "section":
            kwargs["section"] = section
            matches = await matcher.match(content, **kwargs)
        elif current_mode == "line_range":
            kwargs["start_line"] = start_line
            kwargs["end_line"] = end_line
            matches = await matcher.match(content, **kwargs)
        else:
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
            return ResultFormatter.not_found("未找到匹配内容", metadata={"search_mode": current_mode})

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
        return ResultFormatter.error(f"获取文章失败: {str(exc)}")


async def grep_articles(
    article_ids: list[int],
    keyword: str | None = None,
    section: str | None = None,
    mode: str = "auto",
    context_lines: int = 0,
    max_results: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """跨多个文章搜索。"""
    results: list[dict[str, Any]] = []
    articles_with_matches = 0

    for article_id in article_ids:
        single = await grep_article(
            article_id=article_id,
            keyword=keyword,
            section=section,
            mode=mode,
            context_lines=context_lines,
            max_results=max_results,
            **kwargs,
        )
        if single.get("status") == "success":
            articles_with_matches += 1
            data = single.get("data", {})
            results.append(
                {
                    "article_id": article_id,
                    "title": data.get("title"),
                    "matches": data.get("matches", []),
                }
            )

    return ResultFormatter.success(
        data={"results": results},
        metadata={
            "total_articles": len(article_ids),
            "articles_with_matches": articles_with_matches,
            "search_mode": mode,
        },
    )


async def search_articles(
    query: str,
    keywords: str | None = None,
    top_k: int = 10,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """兼容旧接口：转发到 ArticleRetriever。"""
    retriever = ArticleRetriever()
    return await retriever.search_articles(
        query=query,
        keywords=keywords,
        top_k=top_k,
        threshold=threshold,
    )


async def close_resources():
    """关闭检索模块的资源。"""
    import asyncio
    from src.core.api_clients import close_clients
    await asyncio.get_event_loop().run_in_executor(None, close_clients)
