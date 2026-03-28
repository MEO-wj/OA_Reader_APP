"""
消息处理函数 - 处理 OpenAI tool_calls 和技能调用
"""
import asyncio
import importlib
import json
import threading
from typing import Any

from src.chat.context_truncator import (
    truncate_grep_document_result,
    truncate_search_documents_result,
    truncate_tool_output,
)
from src.chat.prompts_runtime import FORM_MEMORY_PROMPT_TEMPLATE
from src.chat.utils import _sanitize_memory_text
from src.core.skill_system import SkillSystem
from src.core.tool_activation import should_enable_read_reference


_tool_loop: asyncio.AbstractEventLoop | None = None
_tool_thread: threading.Thread | None = None
_tool_loop_lock = threading.Lock()
_tool_loop_ready = threading.Event()


def _tool_loop_worker(loop: asyncio.AbstractEventLoop) -> None:
    """后台线程事件循环，供同步入口复用。"""
    asyncio.set_event_loop(loop)
    _tool_loop_ready.set()
    loop.run_forever()

    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


def _get_tool_loop() -> asyncio.AbstractEventLoop:
    """获取或创建后台工具事件循环。"""
    global _tool_loop, _tool_thread

    with _tool_loop_lock:
        if _tool_loop and _tool_thread and _tool_thread.is_alive():
            return _tool_loop

        _tool_loop_ready.clear()
        _tool_loop = asyncio.new_event_loop()
        _tool_thread = threading.Thread(
            target=_tool_loop_worker,
            args=(_tool_loop,),
            daemon=True,
            name="tool-calls-loop",
        )
        _tool_thread.start()

    _tool_loop_ready.wait()
    return _tool_loop


def shutdown_tool_loop() -> None:
    """关闭后台工具事件循环。"""
    global _tool_loop, _tool_thread

    with _tool_loop_lock:
        if not _tool_loop or not _tool_thread:
            return
        loop = _tool_loop
        thread = _tool_thread
        _tool_loop = None
        _tool_thread = None

    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2.0)


async def _dispatch_secondary_tool(tool_name: str, tool_def: dict, function_args: dict) -> str:
    """分发二级工具调用到对应的处理函数（异步版本）

    Args:
        tool_name: 工具名称
        tool_def: 工具定义（包含 handler 信息）
        function_args: 函数参数

    Returns:
        JSON 格式的结果字符串
    """
    handler_path = tool_def.get("handler", "")
    if not handler_path:
        return json.dumps({"error": f"工具 {tool_name} 缺少 handler 定义"}, ensure_ascii=False)

    try:
        module_path, func_name = handler_path.rsplit(".", 1)
        module_mappings = {
            "article_retrieval": "src.core.article_retrieval",
        }
        module_import_path = module_mappings.get(module_path, f"src.core.{module_path}")
        module = importlib.import_module(module_import_path)
        func = getattr(module, func_name)

        if asyncio.iscoroutinefunction(func):
            result = await func(**function_args)
        else:
            result = func(**function_args)

        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"调用失败: {e}"}, ensure_ascii=False)


async def _handle_secondary_tool_call(function_name: str, function_args: dict, skill_system: SkillSystem, activated_skills: set) -> str:
    """处理二级工具调用的辅助函数（异步版本）

    Args:
        function_name: 函数名称
        function_args: 函数参数
        skill_system: 技能系统实例
        activated_skills: 已激活的技能集合

    Returns:
        JSON 格式的结果字符串
    """
    for skill_name in activated_skills:
        skill_info = skill_system.available_skills.get(skill_name)
        if skill_info:
            for tool_def in skill_info.secondary_tools:
                if tool_def["name"] == function_name:
                    return await _dispatch_secondary_tool(function_name, tool_def, function_args)
    return json.dumps({"error": f"工具 {function_name} 未找到或未激活"}, ensure_ascii=False)


async def handle_tool_calls(
    tool_calls: list[Any],
    skill_system: SkillSystem,
    activated_skills: set | None = None,
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    处理 OpenAI 返回的 tool_calls

    Args:
        tool_calls: OpenAI 响应中的 tool_calls 列表
        skill_system: 技能系统实例
        activated_skills: 已激活的技能集合

    Returns:
        工具调用结果消息列表，每个消息包含 role="tool" 和对应的 content
    """
    activated = activated_skills or set()
    tool_messages = []

    for tool_call in tool_calls:
        function_name = tool_call.function.name
        function_args_str = tool_call.function.arguments

        # 解析函数参数（如果有）
        try:
            function_args = json.loads(function_args_str) if function_args_str else {}
        except json.JSONDecodeError:
            function_args = {}

        # 处理不同类型的工具调用
        if function_name == "read_reference":
            # 处理 read_reference 工具调用（异步版本）
            available_skills = getattr(skill_system, "available_skills", {}) or {}
            if not should_enable_read_reference(activated, available_skills):
                content = "错误：read_reference 未激活。请先调用可用的技能。"
            else:
                skill_name = function_args.get("skill_name", "")
                file_path = function_args.get("file_path", "")
                lines = function_args.get("lines", "")
                content = await _read_reference_async(skill_system, skill_name, file_path, lines)
                if not isinstance(content, str):
                    content = str(content)
                content = truncate_tool_output("read_reference", function_name, content)["content"]
        elif function_name == "form_memory":
            # 处理 form_memory 工具调用
            reason = function_args.get("reason", "")
            content = await handle_form_memory(reason, user_id, conversation_id)
        else:
            # 去除 call_skill_ 前缀（如果有）
            skill_name = function_name.replace("call_skill_", "") if function_name.startswith("call_skill_") else function_name

            if skill_name in skill_system.available_skills:
                # 处理技能调用
                content = skill_system.get_skill_content(skill_name)
            else:
                # 处理二级工具调用（异步）
                content = await _handle_secondary_tool_call(function_name, function_args, skill_system, activated)
                if not isinstance(content, str):
                    content = str(content)

                if function_name == "search_articles":
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and "results" in parsed:
                            content = json.dumps(truncate_search_documents_result(parsed), ensure_ascii=False)
                    except (json.JSONDecodeError, TypeError):
                        content = truncate_tool_output("generic", function_name, content)["content"]
                elif function_name == "grep_article":
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and "status" in parsed:
                            content = json.dumps(truncate_grep_document_result(parsed), ensure_ascii=False)
                    except (json.JSONDecodeError, TypeError):
                        content = truncate_tool_output("generic", function_name, content)["content"]
                else:
                    content = truncate_tool_output("generic", function_name, content)["content"]

        # 构建工具响应消息
        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": content
        }
        tool_messages.append(tool_message)

    return tool_messages


async def _read_reference_async(skill_system: SkillSystem, skill_name: str, file_path: str, lines: str = "") -> str:
    """
    异步读取技能参考文件

    Args:
        skill_system: 技能系统实例
        skill_name: 技能名称
        file_path: 参考文件路径
        lines: 可选行范围，格式如 "100-200"

    Returns:
        文件内容字符串
    """
    read_reference = skill_system.read_reference

    # DbSkillSystem.read_reference 是异步函数，需要直接 await。
    if asyncio.iscoroutinefunction(read_reference):
        return await read_reference(skill_name, file_path, lines)

    # 文件系统版本是同步函数，放到线程池避免阻塞事件循环。
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: read_reference(skill_name, file_path, lines)
    )


async def handle_form_memory(
    reason: str = "",
    user_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    """
    处理 form_memory 工具调用

    Args:
        reason: 触发记忆形成的原因
        user_id: 用户ID
        conversation_id: 会话ID

    Returns:
        记忆形成结果消息
    """
    if not user_id:
        return "用户ID不存在，无法形成记忆。"

    if not conversation_id:
        conversation_id = "default"

    # 获取对话历史
    from src.db.memory import MemoryDB
    db = MemoryDB()
    messages = await db.get_conversation(user_id, conversation_id)

    if not messages:
        return "对话历史为空，无需形成记忆。"

    # 构建结构化浓缩 prompt
    prompt = FORM_MEMORY_PROMPT_TEMPLATE.format(
        conversation_lines=chr(10).join([f"{m['role']}: {m['content']}" for m in messages])
    )

    # 调用 LLM 浓缩
    from src.config.settings import Config
    from openai import OpenAI

    config = Config.load()
    client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=config.model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000,
        temperature=0.1,  # 低温度，提高一致性
    )

    content = response.choices[0].message.content or ""

    # 清洗内容，去除 markdown 和 think 标签
    content = _sanitize_memory_text(content)

    # 解析画像和知识（支持结构化格式）
    portrait_text = ""
    knowledge_text = ""

    # 尝试新格式：结构化标签
    if "<必须满足>" in content:
        # 提取各部分内容
        import re

        def extract_section(text, tag):
            tag_name = tag.replace("<", "").replace(">", "")
            # 使用 [\s\S]*? 替代 [^]*? 来匹配任意字符（包括换行）
            pattern = rf'{tag}([\s\S]*?)</{tag_name}>'
            match = re.search(pattern, text)
            return match.group(1).strip() if match else ""

        hard_constraints = extract_section(content, "<必须满足>")
        soft_constraints = extract_section(content, "<优先考虑>")
        risk_tolerance = extract_section(content, "<风险承受>")
        verified_facts = extract_section(content, "<已确认事实>")
        pending_queries = extract_section(content, "<待查询事项>")

        # 合并为统一格式（与后续解析方法兼容）
        portrait_text = f"必须满足：{hard_constraints}\n优先考虑：{soft_constraints}\n风险承受：{risk_tolerance}"
        knowledge_text = f"已确认事实：{verified_facts}\n待查询：{pending_queries}"
    # 尝试旧格式兼容
    elif "【用户画像】" in content:
        parts = content.split("【知识记忆】")
        portrait_text = parts[0].replace("【用户画像】", "").strip()
        knowledge_text = parts[1].strip() if len(parts) > 1 else ""

    # 保存到数据库
    await db.save_profile(user_id, portrait_text, knowledge_text)

    return f"记忆已形成：\n【用户画像】{portrait_text}\n【知识记忆】{knowledge_text}"


def handle_tool_calls_sync(
    tool_calls: list[Any],
    skill_system: SkillSystem,
    activated_skills: set | None = None
) -> list[dict[str, Any]]:
    """
    同步包装器，用于兼容现有代码

    Args:
        tool_calls: OpenAI 响应中的 tool_calls 列表
        skill_system: 技能系统实例
        activated_skills: 已激活的技能集合

    Returns:
        工具调用结果消息列表
    """
    loop = _get_tool_loop()
    future = asyncio.run_coroutine_threadsafe(
        handle_tool_calls(tool_calls, skill_system, activated_skills),
        loop,
    )
    return future.result()
