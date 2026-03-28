"""FastAPI 主入口"""

import asyncio
import inspect
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from migrations.migrate import run_migration
from pathlib import Path

# 导入数据加载脚本
from scripts.import_skills import main as import_skills_main

from src.chat.handlers import shutdown_tool_loop
from src.api.models import ChatRequest, ConversationCreate, HealthResponse, SkillsResponse
from src.api.import_decider import should_run_auto_import
from src.api.admin import router as admin_router
from src.core.api_clients import close_clients
from src.core.api_queue import close_api_queue
from src.core.db import close_pool
from src.core.article_retrieval import close_resources
from src.di.providers import get_chat_service


async def _maybe_await(result: object) -> None:
    if inspect.isawaitable(result):
        await result


@asynccontextmanager
async def lifespan(_app: FastAPI):
    auto_migrate = os.getenv("AUTO_MIGRATE", "false").lower() in {"1", "true", "yes", "on"}
    if auto_migrate:
        ok = await run_migration(auto_repair=True)
        if not ok:
            raise RuntimeError("数据库自动迁移/修复失败，请检查 migrations 日志")

        # 自动导入数据
        auto_import = os.getenv("AUTO_IMPORT", "false").lower() in {"1", "true", "yes", "on"}
        if auto_import:
            try:
                should_import = await should_run_auto_import()
            except Exception as e:
                print(f"⚠️ 导入探测失败，回退为执行导入: {e}")
                should_import = True

            if should_import:
                print("🔄 检测到数据缺失或变更，开始自动导入...")
                try:
                    await import_skills_main(Path("skills"))
                    print("✅ skills 导入完成")
                except Exception as e:
                    print(f"⚠️ 数据导入失败: {e}")
                    # 数据导入失败不阻塞启动，让服务可以正常运行
            else:
                print("✅ 数据已完整且无变更，跳过自动导入")
    yield
    # 关闭顺序与项目并发治理约定保持一致
    await _maybe_await(close_clients())
    await _maybe_await(close_resources())
    await _maybe_await(close_pool())
    await _maybe_await(close_api_queue())
    await _maybe_await(shutdown_tool_loop())


app = FastAPI(
    title="AI Agent API",
    description="通用 AI Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

# 测试环境中 static 目录可能尚未创建，因此关闭目录存在性检查。
app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")

# 挂载管理 API
app.include_router(admin_router)


@app.get("/", response_model=dict)
async def root() -> dict[str, str]:
    """根路径"""
    return {"message": "AI Agent API", "version": "0.1.0"}


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """健康检查"""
    return HealthResponse(status="ok", version="0.1.0")


@app.get("/skills", response_model=SkillsResponse)
async def list_skills() -> SkillsResponse:
    """列出可用技能"""
    from src.core.db_skill_system import DbSkillSystem
    from src.config.settings import Config

    config = Config.load()
    skill_system = await DbSkillSystem.create(config)
    skills = [
        {"name": name, "description": info.description}
        for name, info in skill_system.available_skills.items()
    ]
    return SkillsResponse(
        skills=skills,
        data_source="database",
        skill_count=len(skills)
    )


@app.post("/chat", response_class=StreamingResponse)
async def chat(request: ChatRequest) -> StreamingResponse:
    """SSE 流式聊天接口"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    conversation_id, _title = await db.get_or_create_session(
        request.user_id,
        request.conversation_id,
    )

    service = get_chat_service(
        user_id=request.user_id,
        conversation_id=conversation_id,
    )
    return StreamingResponse(
        service.chat_stream(request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": conversation_id,
        },
    )


@app.get("/chat/history", response_model=dict)
async def get_chat_history(
    user_id: str = Query(min_length=1, max_length=64),
    conversation_id: str = Query(default="default", min_length=1, max_length=64),
) -> dict:
    """获取指定用户的聊天历史。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    messages = await db.get_conversation(user_id, conversation_id)
    return {"user_id": user_id, "conversation_id": conversation_id, "messages": messages}


@app.get("/chat/sessions", response_model=dict)
async def list_sessions(user_id: str = Query(min_length=1, max_length=64)) -> dict:
    """列出用户所有会话。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    sessions = await db.list_sessions(user_id)
    return {"user_id": user_id, "sessions": sessions, "count": len(sessions)}


@app.post("/chat/sessions", response_model=dict)
async def create_session(request: ConversationCreate) -> dict:
    """创建新会话。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    conversation_id = str(uuid.uuid4())[:8]
    title = request.title or "新会话"
    await db.create_session(request.user_id, conversation_id, title)
    return {
        "user_id": request.user_id,
        "conversation_id": conversation_id,
        "title": title,
        "status": "created",
    }


@app.get("/chat/sessions/{conversation_id}", response_model=dict)
async def get_session(
    conversation_id: str,
    user_id: str = Query(min_length=1, max_length=64),
) -> dict:
    """获取指定会话。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    session = await db.get_session(user_id, conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = await db.get_conversation(user_id, conversation_id)
    return {"session": session, "messages": messages}


@app.delete("/chat/sessions/{conversation_id}", response_model=dict)
async def delete_session(
    conversation_id: str,
    user_id: str = Query(min_length=1, max_length=64),
) -> dict:
    """删除指定会话。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    await db.delete_session(user_id, conversation_id)
    return {"status": "ok", "conversation_id": conversation_id}


@app.get("/chat/users", response_model=dict)
async def list_chat_users(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    """列出最近有聊天记录的用户。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    users = await db.list_recent_users(limit=limit)
    return {"users": users, "count": len(users)}


@app.delete("/chat/history", response_model=dict)
async def delete_chat_history(user_id: str = Query(min_length=1, max_length=64)) -> dict:
    """清空指定用户聊天历史与画像。"""
    from src.db.memory import MemoryDB

    db = MemoryDB()
    await db.clear_user_memory(user_id)
    return {"status": "ok", "user_id": user_id}
