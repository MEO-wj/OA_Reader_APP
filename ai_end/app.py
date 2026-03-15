"""AI 服务主应用。"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from flask import Flask, jsonify, request
import requests
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing import TypedDict, Annotated

from ai_end.config import Config
from ai_end.services.load_balancer import AILoadBalancer, ModelConfig
from ai_end.services.queue import AIRequestQueue

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建 Flask 应用
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# 配置
config = Config()

# 数据库连接（复用 backend 的 db 模块）
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
from backend.db import db_session

# Redis 缓存
redis_client = None
try:
    import redis
    redis_client = redis.Redis(
        host=config.redis_host,
        port=config.redis_port,
        db=config.redis_db,
        password=config.redis_password,
        decode_responses=True
    )
    redis_client.ping()
    logger.info("Redis 连接成功")
except Exception as e:
    logger.warning(f"Redis 连接失败: {e}")

cache = None
if redis_client:
    from backend.utils.redis_cache import RedisCache
    cache = RedisCache(redis_client)

# 负载均衡器单例
_load_balancer: Optional[AILoadBalancer] = None
_load_balancer_lock = threading.Lock()

# 消息队列单例
_ai_queue: Optional[AIRequestQueue] = None
_queue_initialized = False

# 缓存编译后的 Agent Graph（按模型配置分桶，避免每次请求重建）
_cached_agents: dict[str, Any] = {}
_cached_agent_lock = threading.Lock()

MEMORY_TTL_SECONDS = 24 * 60 * 60
MEMORY_MAX_ITEMS = 5


def _mask_api_key(api_key: str) -> str:
    """掩码 API Key，只显示前8位和后4位。"""
    if len(api_key) > 12:
        return f"{api_key[:8]}...{api_key[-4:]}"
    return "***"


def _get_load_balancer() -> Optional[AILoadBalancer]:
    global _load_balancer
    if _load_balancer is None:
        with _load_balancer_lock:
            if _load_balancer is None:
                if config.ai_enable_load_balancing and config.ai_models:
                    _load_balancer = AILoadBalancer(config.ai_models)
                    logger.info(f"AI负载均衡器已启用，共 {len(config.ai_models)} 个配置组")
                else:
                    logger.debug("AI负载均衡器未启用或配置为空")
    return _load_balancer


def _create_llm_with_config(model_config: Optional[ModelConfig]) -> ChatOpenAI:
    if model_config:
        logger.info(f"使用负载均衡模型: {model_config.model} @ {model_config.base_url} (key: {_mask_api_key(model_config.api_key)})")

        return ChatOpenAI(
            api_key=model_config.api_key,
            base_url=_normalize_ai_base_url(model_config.base_url),
            model=model_config.model,
            temperature=0.2,
        )

    logger.info(f"使用传统单一配置: {config.ai_model} @ {config.ai_base_url} (key: {_mask_api_key(config.api_key)})")

    return ChatOpenAI(
        api_key=config.api_key,
        base_url=_normalize_ai_base_url(config.ai_base_url),
        model=config.ai_model,
        temperature=0.2,
    )


def _create_llm_for_request() -> tuple[Optional[ModelConfig], ChatOpenAI]:
    load_balancer = _get_load_balancer()
    if load_balancer:
        model_config = load_balancer.get_next_model()
        if model_config:
            logger.info(f"使用负载均衡模型: {model_config.model} @ {model_config.base_url} (key: {_mask_api_key(model_config.api_key)})")

            llm = ChatOpenAI(
                api_key=model_config.api_key,
                base_url=_normalize_ai_base_url(model_config.base_url),
                model=model_config.model,
                temperature=0.2,
            )
            return model_config, llm
        raise RuntimeError("所有AI模型均不可用，请稍后再试。")

    if not (config.api_key and config.ai_base_url and config.ai_model):
        raise RuntimeError("AI服务配置不完整")

    logger.info(f"使用传统单一配置: {config.ai_model} @ {config.ai_base_url} (key: {_mask_api_key(config.api_key)})")

    llm = ChatOpenAI(
        api_key=config.api_key,
        base_url=_normalize_ai_base_url(config.ai_base_url),
        model=config.ai_model,
        temperature=0.2,
    )
    return None, llm


def _is_rate_limit_error(error: Exception) -> bool:
    error_msg = str(error).lower()
    return (
        "429" in error_msg
        or "rate limit" in error_msg
        or "rate_limit" in error_msg
        or "too many requests" in error_msg
        or "quota" in error_msg
    )


def _is_ai_configured() -> bool:
    load_balancer = _get_load_balancer()
    if load_balancer and load_balancer.models:
        return True
    return bool(config.ai_base_url and config.api_key and config.ai_model)


def _normalize_ai_base_url(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url:
        return None
    url = raw_url.rstrip("/")
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def _log_messages(stage: str, messages: list[BaseMessage]) -> None:
    msg_types = {}
    for msg in messages:
        msg_type = msg.__class__.__name__
        msg_types[msg_type] = msg_types.get(msg_type, 0) + 1

    user_question_preview = ""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, str):
                user_question_preview = content[:50] + "..." if len(content) > 50 else content
            break

    logger.info(
        "AI请求 %s - 消息数: %d, 类型: %s, 问题: %s",
        stage,
        len(messages),
        json.dumps(msg_types, ensure_ascii=False),
        user_question_preview,
    )


def generate_embedding(text: str) -> Optional[list[float]]:
    """生成文本的向量嵌入。"""
    try:
        if config.embed_base_url and config.embed_api_key:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.embed_api_key}"
            }
            payload = {
                "model": config.embed_model or "default-model",
                "input": text
            }

            response = requests.post(config.embed_base_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()
            return result["data"][0]["embedding"]
        else:
            logger.error("嵌入服务配置不完整")
            return None

    except Exception as e:
        logger.error(f"生成向量嵌入失败: {e}")
        return None


def search_similar_articles(query_embedding: list[float], top_k: int = 3) -> list[dict[str, Any]]:
    """搜索与查询向量相似的文章。"""
    try:
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"

        recency_weight = max(config.ai_recency_weight, 0.0)
        half_life_days = max(config.ai_recency_half_life_days, 1.0)
        candidate_limit = min(max(top_k * 5, top_k), 50)

        sql = """
        WITH candidate AS (
            SELECT a.id, a.title, a.unit, a.published_on, a.summary, a.content,
                   v.embedding <=> %s::vector AS similarity
            FROM vectors v
            JOIN articles a ON v.article_id = a.id
            ORDER BY v.embedding <=> %s::vector
            LIMIT %s
        )
        SELECT id, title, unit, published_on, summary, content, similarity,
               similarity - %s * exp(-GREATEST(CURRENT_DATE - published_on, 0)::float / %s) AS score
        FROM candidate
        ORDER BY score ASC
        LIMIT %s
        """
        params: list[Any] = [vector_str, vector_str, candidate_limit, recency_weight, half_life_days, top_k]

        with db_session() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            results = cur.fetchall()

        articles = []
        for row in results:
            article = {
                "id": row["id"],
                "title": row["title"],
                "unit": row["unit"],
                "published_on": row["published_on"],
                "summary": row["summary"],
                "content": row["content"],
                "similarity": float(row["similarity"]),
                "score": float(row["score"])
            }
            articles.append(article)

        return articles

    except Exception as e:
        logger.error(f"搜索相似文章失败: {e}")
        return []


def _memory_key(user_id: str) -> str:
    return f"ai:mem:{user_id}"


def _load_short_memory(user_id: str) -> list[dict[str, str]]:
    if not cache:
        return []
    raw = cache.get(_memory_key(user_id), default=[])
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _save_short_memory(user_id: str, question: str, answer: str) -> None:
    if not cache:
        return
    history = _load_short_memory(user_id)
    history.append({"user": question, "assistant": answer})
    history = history[-MEMORY_MAX_ITEMS:]
    cache.set(_memory_key(user_id), history, expire_seconds=MEMORY_TTL_SECONDS)


def _build_memory_messages(history: list[dict[str, str]]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        user_text = (item.get("user") or "").strip()
        assistant_text = (item.get("assistant") or "").strip()
        if user_text:
            messages.append(HumanMessage(content=user_text))
        if assistant_text:
            messages.append(AIMessage(content=assistant_text))
    return messages


def _build_system_prompt(top_k_hint: int, display_name: Optional[str] = None) -> str:
    time_now = datetime.now()
    identity_hint = f"当前用户的名字：{display_name}。可酌情称呼，但不强制。\n" if display_name else "\n"
    return (
        f"""
你是校内OA管理员瑞德，专注于帮人查找和解读OA系统中的相关文章。你会根据问题的具体需求，自主判断是否需要检索文章内容来为你提供准确信息。
**你的工作方式：**
1. **常规问题**：如果用户的提问不涉及具体文章内容（例如流程咨询、功能指引），你会直接基于知识作答。
2. **文章查询**：当问题涉及具体政策、通知、文章细节时，你会主动检索相关文章，确保信息准确。
3. **检索设置**：检索时要根据问题复杂度自动选择：
   - **简要检索** (`detail_level: brief`)：适用于关键词查询、简单事实确认。
   - **全文检索** (`detail_level: full`)：适用于复杂分析、政策解读或多文章对比。
   - **检索数量** (`top_k`)：通常设置为 `{top_k_hint}` 篇左右，确保覆盖核心内容，如果返回的结果你认为无法覆盖，你将会进行下一次搜索，最多多搜索一次。
**！！注意：**
- 你要严格依据OA系统内现有信息作答，不编造未收录的内容。
- 如需深入分析，建议用户提供具体的关键词或背景，你会更精准地定位文章。
- 如果用户的问题与OA系统无关，你会礼貌提醒并引导其关注相关事务。
{identity_hint}
当前日期和时间：{time_now.strftime("%Y年%m月%d日 %H:%M")}
"""
    )


@tool("vector_search")
def vector_search_tool(query: str, top_k: int = 3, detail_level: str = "brief") -> str:
    """OA向量检索工具：返回相关文章内容与摘要。"""
    normalized_top_k = max(1, min(10, int(top_k)))
    normalized_level = "full" if detail_level == "full" else "brief"
    logger.info(
        "AI工具调用 vector_search: %s",
        json.dumps(
            {"query": query, "top_k": normalized_top_k, "detail_level": normalized_level},
            ensure_ascii=False,
            default=str,
        ),
    )
    embedding = generate_embedding(query)
    if not embedding:
        payload = {"error": "embedding_failed", "documents": [], "related_articles": []}
        return json.dumps(payload, ensure_ascii=False)

    articles = search_similar_articles(embedding, normalized_top_k)
    related_articles = _build_related_articles(articles)
    documents = []
    for article in articles:
        doc = {
            "id": article.get("id"),
            "title": article.get("title"),
            "unit": article.get("unit"),
            "published_on": _serialize_value(article.get("published_on")),
            "summary": article.get("summary"),
        }
        if normalized_level == "full":
            doc["content"] = article.get("content") or ""
        else:
            doc["content_snippet"] = _truncate_text(article.get("content"))
            doc["summary_snippet"] = _truncate_text(article.get("summary"))
        documents.append(doc)

    payload = {
        "detail_level": normalized_level,
        "documents": documents,
        "related_articles": related_articles,
    }
    payload_text = json.dumps(payload, ensure_ascii=False, default=str)
    logger.info(
        "AI工具返回 vector_search: %s",
        json.dumps(
            {"len": len(payload_text), "preview": payload_text[:500]},
            ensure_ascii=False,
            default=str,
        ),
    )
    return payload_text


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _build_agent_with_config(fixed_model_config: Optional[ModelConfig]) -> Any:
    tools = [vector_search_tool]
    llm = _create_llm_with_config(fixed_model_config)
    llm_with_tools = llm.bind_tools(tools)

    initial_config = fixed_model_config

    def agent_node(state: AgentState) -> dict[str, list[BaseMessage]]:
        load_balancer = _get_load_balancer()
        max_tries = len(load_balancer.models) if load_balancer else 1
        last_error: Optional[Exception] = None

        for attempt in range(max_tries):
            try:
                if attempt == 0:
                    current_llm_config = initial_config
                else:
                    current_llm_config, _ = _create_llm_for_request()

                current_llm = _create_llm_with_config(current_llm_config)
                current_llm_with_tools = current_llm.bind_tools(tools)

                _log_messages("before_llm", state["messages"])
                response = current_llm_with_tools.invoke(state["messages"])
                _log_messages("after_llm", state["messages"] + [response])

                return {"messages": state["messages"] + [response]}

            except Exception as e:
                last_error = e
                is_rate_limit = _is_rate_limit_error(e)

                if attempt == 0:
                    if initial_config:
                        model_info = f"模型: {initial_config.model} @ {initial_config.base_url} (key: {_mask_api_key(initial_config.api_key)})"
                    else:
                        model_info = f"传统配置: {config.ai_model} @ {config.ai_base_url}"
                else:
                    model_info = "重试模型"

                if is_rate_limit and load_balancer and attempt < max_tries - 1:
                    if attempt == 0 and initial_config:
                        logger.warning(f"[429] {model_info} - 切换模型重试 (尝试 {attempt + 1}/{max_tries})")
                        load_balancer.mark_model_429(initial_config)
                    else:
                        logger.warning(f"[429] {model_info} - 继续切换模型重试 (尝试 {attempt + 1}/{max_tries})")
                    continue
                else:
                    logger.error(f"[AI请求失败] {model_info} - 错误: {e}")
                    raise

        if last_error:
            raise last_error
        raise Exception("所有AI模型均不可用，请稍后再试")

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    graph.set_entry_point("agent")
    return graph.compile()


def _agent_cache_key(model_config: Optional[ModelConfig]) -> str:
    if not model_config:
        return "__default__"
    return f"{model_config.base_url}|{model_config.model}|{model_config.api_key}"


def _get_cached_agent(fixed_model_config: Optional[ModelConfig]) -> Any:
    """按模型配置获取缓存的 Agent Graph。"""
    cache_key = _agent_cache_key(fixed_model_config)
    cached = _cached_agents.get(cache_key)
    if cached is not None:
        return cached

    with _cached_agent_lock:
        cached = _cached_agents.get(cache_key)
        if cached is None:
            cached = _build_agent_with_config(fixed_model_config)
            _cached_agents[cache_key] = cached
    return cached


def _execute_ai_request(question: str, top_k_hint: int, display_name: Optional[str], user_id: str) -> dict[str, Any]:
    """执行 AI 请求的公共逻辑。"""
    model_config_for_this_request = None
    load_balancer = _get_load_balancer()
    if load_balancer and load_balancer.models:
        model_config_for_this_request = load_balancer.get_next_model()

    history = _load_short_memory(user_id) if user_id else []
    messages: list[BaseMessage] = [
        SystemMessage(content=_build_system_prompt(top_k_hint, display_name)),
        *_build_memory_messages(history),
        HumanMessage(content=question),
    ]

    agent = _get_cached_agent(model_config_for_this_request)
    result = agent.invoke({"messages": messages})
    final_messages = result.get("messages", messages)
    answer = _extract_answer(final_messages) or "当前服务不可用，请稍后再试。"
    related_articles = _extract_related_articles(final_messages)

    if user_id:
        _save_short_memory(user_id, question, answer)

    return {"answer": answer, "related_articles": related_articles}


def _extract_related_articles(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    related: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        items = payload.get("related_articles")
        if isinstance(items, list):
            related = items
    return related


def _extract_answer(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            if getattr(message, "tool_calls", None):
                continue
            return message.content
    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content:
            return message.content
    return ""


def _truncate_text(text: Optional[str], limit: int = 80) -> str:
    if not text:
        return ""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}…"


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(val) for key, val in value.items()}
    return value


def _build_related_articles(articles: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    related = []
    for article in articles:
        content_snippet = _truncate_text(article.get("content"))
        summary_snippet = _truncate_text(article.get("summary"))
        related.append(
            {
                "id": article.get("id"),
                "title": article.get("title"),
                "unit": article.get("unit"),
                "published_on": _serialize_value(article.get("published_on")),
                "similarity": article.get("similarity"),
                "content_snippet": content_snippet,
                "summary_snippet": summary_snippet,
            }
        )
    return related


def _initialize_queue() -> None:
    global _ai_queue, _queue_initialized
    if _queue_initialized:
        return
    if config.ai_queue_enabled:
        _ai_queue = AIRequestQueue(
            app=app,
            max_size=config.ai_queue_max_size,
            timeout=config.ai_queue_timeout,
        )
        _ai_queue.set_handler(_process_ai_request_internal)
        _ai_queue.start()
        _queue_initialized = True
        logger.info("AI请求队列已启动")


def _process_ai_request_internal(data: dict[str, Any]) -> dict[str, Any]:
    """队列处理函数：实际执行AI请求。"""
    question = data.get("question")
    top_k_hint = data.get("top_k", 3)
    display_name = data.get("display_name")
    user_id = data.get("user_id", "")

    if not _is_ai_configured():
        return {"error": "AI服务配置不完整"}

    return _execute_ai_request(question, top_k_hint, display_name, user_id)


@app.route('/ask', methods=['POST'])
def ask_question():
    """AI问答API。"""
    try:
        data = request.get_json()

        if not data or 'question' not in data:
            return jsonify({"error": "请求参数错误，缺少question字段"}), 400

        question = data['question']
        top_k_hint = data.get('top_k', 3)
        display_name = data.get('display_name')

        if not _is_ai_configured():
            return jsonify({"error": "AI服务配置不完整"}), 500

        user_id = data.get('user_id', '')

        # 检查是否使用队列
        if _ai_queue and config.ai_queue_enabled:
            queue_data = {
                "question": question,
                "top_k": top_k_hint,
                "display_name": display_name,
                "user_id": user_id,
            }

            logger.info(
                "AI请求入队: %s",
                json.dumps(
                    {"question": question, "user_id": user_id, "queue_enabled": True},
                    ensure_ascii=False,
                ),
            )

            success, result = _ai_queue.enqueue(queue_data)
            if not success:
                return jsonify({"error": result}), 503

            return jsonify(result), 200
        else:
            result = _execute_ai_request(question, top_k_hint, display_name, user_id)
            return jsonify(result), 200

    except Exception as e:
        logger.error(f"AI问答失败: {e}")
        return jsonify({"error": "AI问答失败"}), 500


@app.route('/clear_memory', methods=['POST'])
def clear_memory():
    """清空用户的AI短记忆缓存。"""
    try:
        data = request.get_json()
        user_id = data.get('user_id') if data else None

        if not user_id:
            return jsonify({"error": "用户信息缺失"}), 400

        if cache:
            cleared = cache.delete(_memory_key(user_id))
        else:
            cleared = True

        logger.info("AI记忆清理: %s", json.dumps({"user_id": user_id, "cleared": cleared}, ensure_ascii=False))
        return jsonify({"cleared": bool(cleared)}), 200
    except Exception as e:
        logger.error(f"AI记忆清理失败: {e}")
        return jsonify({"error": "AI记忆清理失败"}), 500


@app.route('/embed', methods=['POST'])
def embed_text():
    """生成文本向量嵌入。"""
    try:
        data = request.get_json()
        text = data.get("text") if data else None

        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "请求参数错误，缺少text字段"}), 400

        embedding = generate_embedding(text)
        if embedding is None:
            return jsonify({"error": "生成向量嵌入失败"}), 503

        return jsonify({"embedding": embedding}), 200
    except Exception as e:
        logger.error(f"生成向量嵌入失败: {e}")
        return jsonify({"error": "生成向量嵌入失败"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查。"""
    return jsonify({"status": "ok"}), 200


# 启动时初始化队列
@app.before_request
def init_queue_once():
    global _queue_initialized
    if not _queue_initialized:
        _initialize_queue()
        _queue_initialized = True


if __name__ == '__main__':
    app.run(host=config.flask_host, port=config.flask_port, debug=False)
