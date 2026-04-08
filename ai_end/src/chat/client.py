"""
聊天客户端 - OpenAI API 集成与技能系统

TDD GREEN 阶段：实现通过测试的代码
"""
import asyncio
import inspect
import logging
import re
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

from openai import AsyncOpenAI, OpenAI
from src.ui import Colors, print_step, print_error
from src.chat.handlers import handle_tool_calls_sync, shutdown_tool_loop
from src.chat.utils import _sanitize_memory_text
from src.chat.context_budget import (
    BudgetAction,
    create_budget_check,
    estimate_tokens,
)
from src.config.settings import Config
from src.core.skill_adapter import SkillBackend
from src.core.api_queue import get_api_queue
from src.core.api_clients import get_llm_client, close_clients
from src.core.db import close_pool
from src.core.article_retrieval import close_resources
from src.di.providers import get_history_manager, get_memory_manager, get_skill_system
from src.chat.prompts_runtime import SYSTEM_PROMPT_TEMPLATE


class ChatClient:
    """聊天客户端，集成 OpenAI API 和技能系统"""

    # 默认系统提示词模板（从 prompts_runtime 引用）
    DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE

    @property
    def user_id(self) -> str | None:
        return getattr(self, "_user_id", None)

    @user_id.setter
    def user_id(self, value: str | None) -> None:
        self._user_id = value
        self._propagate_manager_context()

    @property
    def conversation_id(self) -> str:
        return getattr(self, "_conversation_id", "default")

    @conversation_id.setter
    def conversation_id(self, value: str | None) -> None:
        self._conversation_id = value or "default"
        self._propagate_manager_context()

    def _init_state(
        self,
        config: Config,
        skill_system: Any,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """初始化共享状态，供同步/异步构造复用。"""
        self.config = config
        self.client = get_llm_client(
            factory=lambda: OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )
        )
        self.skill_system = skill_system
        self.messages: list[dict[str, Any]] = []
        self.activated_skills: set[str] = set()
        self._user_id = user_id
        self._conversation_id = conversation_id or "default"
        self._memory_manager = get_memory_manager(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            config=config,
            completion_sync=self._create_memory_completion_sync,
        )
        self._history_manager = get_history_manager(
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            config=config,
            completion_sync=self._create_title_completion_sync,
        )
        self._propagate_manager_context()
        self.round_count = 0  # 对话轮数计数
        self.usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @classmethod
    async def create(
        cls,
        config: Config,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> "ChatClient":
        """
        异步工厂方法，创建聊天客户端

        Args:
            config: 配置对象
            user_id: 用户ID（可选）
            conversation_id: 会话ID（可选）

        Returns:
            ChatClient 实例
        """
        self = cls.__new__(cls)
        skill_system = get_skill_system(backend=SkillBackend.DATABASE)
        await skill_system.load_skills()
        self._init_state(config, skill_system, user_id, conversation_id)
        return self

    def __init__(self, config: Config):
        """同步初始化（兼容旧调用路径，使用文件系统技能系统）。"""
        skill_system = get_skill_system(
            backend=SkillBackend.FILESYSTEM,
            skills_dir=config.skills_dir,
        )
        self._init_state(config, skill_system)

    def _build_system_prompt(
        self,
        portrait: str | None = None,
        knowledge: str | None = None
    ) -> str:
        """
        构建系统提示词（结构化版）

        Args:
            portrait: 用户画像（可选）
            knowledge: 知识记忆（可选）

        Returns:
            包含技能名称列表和结构化画像的系统提示词
        """
        # 只输出技能名称，不输出描述（描述在工具定义中已有）
        skills_list = []
        for skill_name in sorted(self.skill_system.available_skills.keys()):
            skills_list.append(f"- {skill_name}")

        skills_text = "\n".join(skills_list)

        # 构建画像章节
        if portrait or knowledge:
            sections = self._parse_profile_to_sections(
                portrait or "",
                knowledge or ""
            )
            profile_section = f"""## 用户画像 - 决策要素

### <必须满足>
{sections['hard_constraints']}
</必须满足>

### <优先考虑>
{sections['soft_constraints']}
</优先考虑>

### <风险承受>
{sections['risk_tolerance']}
</风险承受>

### <已确认事实>
{sections['verified_facts']}
</已确认事实>

### <待查询事项>
{sections['pending_queries']}
</待查询事项>"""
        else:
            profile_section = "## 用户画像 - 决策要素\n\n暂无用户画像信息。"

        # 构建系统提示词
        system_prompt = self.DEFAULT_SYSTEM_PROMPT.format(
            skills_list=skills_text if skills_text else "暂无可用技能",
            profile_section=profile_section
        )

        return system_prompt

    def _parse_profile_to_sections(
        self,
        portrait: str,
        knowledge: str
    ) -> dict[str, str]:
        """
        将画像和知识解析为结构化分层。

        Args:
            portrait: 用户画像 JSON（hard_constraints, soft_constraints, risk_tolerance）
            knowledge: 知识记忆 JSON（verified_facts, pending_queries）

        Returns:
            包含各分层的字典
        """
        import json

        # 解析 portrait JSON
        portrait_data = {}
        if portrait:
            try:
                portrait_data = json.loads(portrait)
            except json.JSONDecodeError:
                pass

        # 解析 knowledge JSON
        knowledge_data = {}
        if knowledge:
            try:
                knowledge_data = json.loads(knowledge)
            except json.JSONDecodeError:
                pass

        return {
            "hard_constraints": "\n".join(f"- {item}" for item in portrait_data.get("hard_constraints", [])) or "（暂无）",
            "soft_constraints": "\n".join(f"- {item}" for item in portrait_data.get("soft_constraints", [])) or "（暂无）",
            "risk_tolerance": "\n".join(f"- {item}" for item in portrait_data.get("risk_tolerance", [])) or "（暂无）",
            "verified_facts": "\n".join(f"- {item}" for item in knowledge_data.get("verified_facts", [])) or "（暂无）",
            "pending_queries": "\n".join(f"- {item}" for item in knowledge_data.get("pending_queries", [])) or "（暂无）",
        }

    @staticmethod
    def _sanitize_memory_text(text: str) -> str:
        """清洗记忆文本，去除 think 标签和低价值噪声符号。"""
        if not text:
            return ""

        cleaned = str(text)
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<thinking>.*?</thinking>", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = cleaned.replace("**", "")

        lines: list[str] = []
        for raw in cleaned.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line in {"#", "##", "###", "---", "___", "***"}:
                continue
            lines.append(line)

        return "\n".join(lines).strip()

    def _is_database_skill_system(self) -> bool:
        """当前技能系统是否来自数据库。"""
        return getattr(self.skill_system, "data_source", "") == "database"

    def _propagate_manager_context(self) -> None:
        """将当前会话上下文同步到子管理器。"""
        memory_manager = getattr(self, "_memory_manager", None)
        history_manager = getattr(self, "_history_manager", None)
        if memory_manager is not None:
            memory_manager.user_id = self.user_id
            memory_manager.conversation_id = self.conversation_id
        if history_manager is not None:
            history_manager.user_id = self.user_id
            history_manager.conversation_id = self.conversation_id

    async def load_context(self) -> list[dict[str, Any]]:
        """加载对话历史（不含 system prompt）。"""
        return await self._history_manager.load()

    async def form_memory(self) -> None:
        """形成用户记忆：浓缩画像和知识"""
        if not self.user_id:
            return

        await self._memory_manager.form_memory(self.messages)
        self.round_count = 0

    async def apply_compact(self) -> bool:
        """
        执行上下文压缩。

        Returns:
            bool: 压缩是否成功
        """
        from src.chat.compact import compact_messages

        # 1. 保留 system prompt 和最近 5 条消息
        system = self.messages[0] if self.messages else None
        recent = self.messages[-5:] if len(self.messages) > 5 else []

        # 2. 压缩 token 预算检查（Critical 4）
        # 估算压缩所需空间：prompt 约 500 tokens + 压缩输出约 800 tokens
        estimated_compact_tokens = 1300
        current_tokens = estimate_tokens(self.messages)
        budget_check = create_budget_check(self.config)
        if current_tokens + estimated_compact_tokens > self.config.max_tokens * 0.95:
            logger.warning("压缩所需空间不足，跳过压缩")
            return False

        # 3. 生成压缩摘要
        summary, response = await compact_messages(self.messages)

        # 4. 记录压缩 token 消耗（Critical 4）
        if response is not None:
            self._record_usage_data(getattr(response, "usage", None))

        # 5. 检测压缩是否成功（Critical 3）
        # 成功时返回单条 assistant 消息（结构化摘要）
        # 失败时返回原始消息列表
        compaction_success = (
            len(summary) == 1 and summary[0].get("role") == "assistant"
        )

        if not compaction_success:
            logger.warning("对话压缩失败，返回原始消息")
            return False

        # 5. 替换消息历史
        if system:
            self.messages = [system] + summary + recent
        else:
            self.messages = summary + recent

        # 6. 重置 round_count（Critical 1）
        self.round_count = 0

        # 7. 持久化到数据库（Critical 2）
        if self.user_id:
            await self.save_compact_history(self.messages)

        return True

    async def save_compact_history(self, messages: list[dict[str, Any]]) -> None:
        """保存压缩后的对话历史（Critical 2）"""
        from src.db.memory import MemoryDB

        db = MemoryDB()
        try:
            # 使用新的压缩消息列表替换原始历史
            # 关键：保留 user_id, conversation_id 不变，对用户透明
            await db.replace_conversation(self.user_id, messages, self.conversation_id)
        except Exception as e:
            # 失败时记录日志但不抛出异常，避免打断 SSE stream
            logger.warning(f"保存压缩历史失败: {e}")

    async def generate_title(self) -> str:
        """根据会话首轮对话生成短标题。"""
        if not self.user_id:
            return "新会话"
        messages = await self._history_manager.load()
        if not messages:
            return "新会话"

        first_user_msg = ""
        first_assistant_msg = ""
        for msg in messages:
            role = msg.get("role")
            content = str(msg.get("content", ""))
            if role == "user" and not first_user_msg:
                first_user_msg = content[:100]
            elif role == "assistant" and not first_assistant_msg:
                first_assistant_msg = content[:100]
            if first_user_msg and first_assistant_msg:
                break

        if not first_user_msg:
            return "新会话"

        return await self._history_manager.generate_title(
            first_user_msg,
            first_assistant_msg,
        )

    def _create_memory_completion_sync(self, prompt: str) -> Any:
        return self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )

    def _create_title_completion_sync(self, prompt: str) -> Any:
        return self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
        )

    def chat(self, user_input: str) -> str:
        """
        主聊天循环，处理 tool_calls 直到 AI 直接回复

        Args:
            user_input: 用户输入

        Returns:
            AI 的回复文本
        """
        # 初始化消息列表（如果为空）
        if not self.messages:
            system_prompt = self._build_system_prompt()
            self.messages.append({"role": "system", "content": system_prompt})

        # 添加用户消息
        self.messages.append({"role": "user", "content": user_input})

        # 预算监控（方案 C-1：轻量版）
        budget_check = create_budget_check(self.config)
        estimated_usage = estimate_tokens(self.messages)
        budget_result = budget_check.check(estimated_usage)

        if budget_result.action == BudgetAction.WARNING:
            print(f"{Colors.YELLOW}⚠️ {budget_result.message}{Colors.END}")
        elif budget_result.action == BudgetAction.CRITICAL:
            print(f"{Colors.YELLOW}⚠️⚠️ {budget_result.message}{Colors.END}")
        elif budget_result.action == BudgetAction.BLOCK:
            print(f"{Colors.RED}❌ {budget_result.message}{Colors.END}")
            return budget_result.message

        # 循环处理直到 AI 直接回复（不调用工具）
        # 注意：依赖 context budget + compact 机制防止无限循环
        iteration = 0
        while True:
            iteration += 1
            # 提示用户正在发送请求
            print(f"{Colors.CYAN}⏳ 正在发送请求给 AI...{Colors.END}")

            # 调用 OpenAI API
            response = get_api_queue().submit_sync(
                "llm",
                self._create_completion_sync,
                self.messages,
                self.skill_system.build_tools_definition(self.activated_skills),
            )

            # 记录 token 用量（如果 API 返回 usage）
            self._record_usage(response)

            # 调试：打印响应信息
            print(f"{Colors.GREEN}✓ 已收到 AI 回复{Colors.END}")
            print(f"{Colors.CYAN}📝 API 调用迭代 {iteration}{Colors.END}")
            print(f"{Colors.CYAN}   消息数量: {len(self.messages)}{Colors.END}")

            # 检查响应是否有效
            if not response.choices or len(response.choices) == 0:
                print_error(f"API 返回了空响应 (迭代 {iteration})")
                print(f"响应对象: {response}")
                # 检查是否有其他有用的信息
                if hasattr(response, 'usage'):
                    print(f"Usage: {response.usage}")
                return "抱歉，服务暂时无法响应，请稍后再试。"

            # 获取助手的回复
            assistant_message = response.choices[0].message

            # 添加助手消息到历史
            self.messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": assistant_message.tool_calls
            })

            # 如果没有 tool_calls，说明 AI 直接回复了
            if not assistant_message.tool_calls:
                return assistant_message.content or ""

            # 处理 tool_calls
            batch_num = sum(1 for msg in self.messages if msg.get("role") == "assistant" and "tool_calls" in msg)
            print_step("🔧", "工具调用", f"批次 {batch_num + 1}")

            # 收集和分类工具调用
            skill_calls = []  # 技能调用
            secondary_tools_by_skill: dict[str, list[tuple[str, str]]] = {}  # 二级工具按技能分组 {skill_name: [(tool_name, arguments), ...]}
            read_reference_calls = []  # read_reference 调用

            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                arguments = tool_call.function.arguments

                # 检查是否是技能调用，如果是则激活二级工具
                if function_name in self.skill_system.available_skills:
                    if function_name not in self.activated_skills:
                        self.activated_skills.add(function_name)
                    skill_calls.append(function_name)
                elif function_name == "read_reference":
                    import json
                    try:
                        args_dict = json.loads(arguments) if arguments else {}
                        skill_name = args_dict.get("skill_name", "")
                        file_path = args_dict.get("file_path", "")
                        read_reference_calls.append((skill_name, file_path))
                    except:
                        read_reference_calls.append(("", arguments or ""))
                else:
                    # 二级工具调用 - 查找所属技能
                    found_skill = None
                    for skill_name, skill_info in self.skill_system.available_skills.items():
                        if skill_info.secondary_tools:
                            for tool_def in skill_info.secondary_tools:
                                if tool_def.get("name") == function_name:
                                    found_skill = skill_name
                                    break
                        if found_skill:
                            break

                    if found_skill:
                        if found_skill not in secondary_tools_by_skill:
                            secondary_tools_by_skill[found_skill] = []
                        secondary_tools_by_skill[found_skill].append((function_name, arguments))

            # 显示技能调用
            if skill_calls:
                for skill_name in skill_calls:
                    print(f"{Colors.GREEN}   ✓ 技能调用: {Colors.BOLD}{skill_name}{Colors.END}")
                    skill_content = self.skill_system.get_skill_content(skill_name)
                    if skill_content:
                        print(f"{Colors.GREEN}      内容长度: {len(skill_content)} 字符{Colors.END}")
                    skill_info = self.skill_system.get_skill_info(skill_name)
                    if skill_info and skill_info.verification_token:
                        print(f"{Colors.GREEN}      验证暗号: {Colors.BOLD}{skill_info.verification_token}{Colors.END}")

            # 显示二级工具调用（按技能分组）
            if secondary_tools_by_skill:
                for skill_name, tools in secondary_tools_by_skill.items():
                    print(f"{Colors.YELLOW}   📦 二级工具 [{skill_name}]:{Colors.END}")
                    for tool_name, arguments in tools:
                        print(f"{Colors.YELLOW}      • {tool_name}{Colors.END}")
                        if self._is_database_skill_system():
                            print(f"{Colors.CYAN}        🗄️ 正在调用数据库: {tool_name}{Colors.END}")
                        # 显示调用参数
                        try:
                            import json
                            args_dict = json.loads(arguments) if arguments else {}
                            if args_dict:
                                # 格式化显示参数
                                params_str = ", ".join(f"{k}={repr(v)[:30]}" for k, v in args_dict.items())
                                print(f"{Colors.YELLOW}        参数: {params_str}{Colors.END}")
                        except (json.JSONDecodeError, TypeError):
                            if arguments:
                                print(f"{Colors.YELLOW}        参数: {arguments[:50]}...{Colors.END}")

            # 显示 read_reference 调用
            if read_reference_calls:
                for skill_name, file_path in read_reference_calls:
                    print(f"{Colors.CYAN}   📖 read_reference{Colors.END}")
                    if self._is_database_skill_system():
                        print(f"{Colors.CYAN}      🗄️ 正在调用数据库: read_reference{Colors.END}")
                    if skill_name:
                        print(f"{Colors.CYAN}      技能: {Colors.BOLD}{skill_name}{Colors.END}")
                    if file_path:
                        print(f"{Colors.CYAN}      文件: {Colors.BOLD}{file_path}{Colors.END}")

            tool_messages = handle_tool_calls_sync(
                assistant_message.tool_calls,
                self.skill_system,
                self.activated_skills
            )

            # 显示工具响应摘要
            print(f"{Colors.CYAN}📨 返回 AI 的工具响应: {len(tool_messages)} 条{Colors.END}")
            if len(tool_messages) > 0:
                total_chars = sum(len(tm.get("content", "")) for tm in tool_messages)
                print(f"{Colors.CYAN}   总字符数: {total_chars}{Colors.END}")

                # 解析并显示每个工具返回的摘要
                for tm in tool_messages:
                    content = tm.get("content", "")
                    try:
                        import json
                        result = json.loads(content)
                        # 根据 tool_call_id 找到对应的工具名称
                        tool_name = "unknown"
                        for tc in assistant_message.tool_calls:
                            if tc.id == tm.get("tool_call_id"):
                                fn_name = tc.function.name
                                if fn_name in self.skill_system.available_skills:
                                    tool_name = f"skill:{fn_name}"
                                else:
                                    tool_name = fn_name
                                break

                        print(f"{Colors.CYAN}   └─ {tool_name}:{Colors.END}")

                        # 根据不同工具类型显示不同摘要
                        if tool_name == "search_articles" and "results" in result:
                            results = result.get("results", [])
                            print(f"{Colors.CYAN}      找到 {len(results)} 条文档{Colors.END}")
                            for r in results[:3]:  # 只显示前3条
                                title = r.get("title", "未知标题")[:40]
                                sim = r.get("rerank_score") or r.get("ebd_similarity")
                                if sim:
                                    print(f"{Colors.CYAN}        • {title}... (相似度: {sim:.2f}){Colors.END}")
                                else:
                                    print(f"{Colors.CYAN}        • {title}...{Colors.END}")
                            if len(results) > 3:
                                print(f"{Colors.CYAN}        ... 还有 {len(results) - 3} 条{Colors.END}")

                        elif tool_name == "grep_article":
                            # 兼容新格式（status 字段）和旧格式（直接返回 error）
                            if result.get("status") == "success":
                                matches = result.get("data", {}).get("matches", [])
                                print(f"{Colors.CYAN}      ✓ 找到 {len(matches)} 个匹配{Colors.END}")
                                for m in matches[:2]:
                                    content_preview = m.get("content", "").replace("\n", " ")[:60]
                                    print(f"{Colors.CYAN}        • {content_preview}...{Colors.END}")
                            elif result.get("status") in ["not_found", "error"]:
                                # 新格式错误
                                error_msg = result.get("error", "未知错误")
                                print(f"{Colors.RED}      ✗ {error_msg}{Colors.END}")
                            elif "error" in result:
                                # 旧格式错误
                                error_msg = result.get("error", "未知错误")
                                print(f"{Colors.RED}      ✗ {error_msg}{Colors.END}")
                            else:
                                # 未知格式，显示完整结果
                                print(f"{Colors.YELLOW}      ? 未知格式: {str(result)[:100]}{Colors.END}")

                        elif isinstance(result, dict) and "error" in result:
                            error_msg = result.get("error", "未知错误")
                            print(f"{Colors.RED}      ✗ 错误: {error_msg}{Colors.END}")

                    except (json.JSONDecodeError, TypeError):
                        # 不是 JSON，显示文本摘要
                        preview = content[:100].replace("\n", " ")
                        print(f"{Colors.CYAN}   预览: {preview}...{Colors.END}")

            # 添加工具消息到历史
            self.messages.extend(tool_messages)

        # 超过最大迭代次数，返回最后的回复
        return self.messages[-1].get("content", "")

    def _create_completion_sync(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        return self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=tools,
        )

    async def _create_completion_stream_async(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncGenerator[Any, None]:
        """
        创建流式补全请求（异步）。
        """
        async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )
        stream = await async_client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=tools,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            yield chunk

    async def _handle_tool_calls_async(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        异步处理工具调用，并将工具消息写入历史。
        """
        from src.chat.handlers import handle_tool_calls

        tool_calls_formatted = []
        for tc in tool_calls:
            function = tc.get("function", {})
            tool_calls_formatted.append(
                {
                    "id": tc.get("id", ""),
                    "function": {
                        "name": function.get("name", ""),
                        "arguments": function.get("arguments", ""),
                    },
                }
            )

        class _ToolFunction:
            def __init__(self, name: str, arguments: str):
                self.name = name
                self.arguments = arguments

        class _ToolCall:
            def __init__(self, call_id: str, name: str, arguments: str):
                self.id = call_id
                self.function = _ToolFunction(name, arguments)

        converted = [
            _ToolCall(
                call_id=item.get("id", ""),
                name=item.get("function", {}).get("name", ""),
                arguments=item.get("function", {}).get("arguments", ""),
            )
            for item in tool_calls_formatted
        ]

        tool_messages = await handle_tool_calls(
            converted,
            self.skill_system,
            self.activated_skills,
            self.user_id,
            self.conversation_id,
        )
        self.messages.extend(tool_messages)
        return tool_messages

    async def chat_stream_async(self, user_input: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        异步流式聊天，输出技能/工具/文本事件。
        """
        is_new_runtime_session = not self.messages

        # 第一次初始化固定 system prompt
        if is_new_runtime_session:
            self.messages.append({"role": "system", "content": self._build_system_prompt()})

        # 仅按 user/assistant 条数对齐数据库历史，避免 system 消息导致错位。
        current_history_count = sum(
            1 for msg in self.messages if msg.get("role") in {"user", "assistant"}
        )
        history = await self.load_context()
        history_empty = not history
        profile_loaded = False
        profile_injected = False
        portrait = ""
        portrait_len = 0
        knowledge_len = 0

        # 仅在新会话首次请求时加载画像，不修改主 system prompt。
        if is_new_runtime_session and history_empty and self.user_id:
            profile = await self._history_manager.memory_db.get_profile(self.user_id)
            if profile:
                profile_loaded = True
                portrait = self._sanitize_memory_text(str(profile.get("portrait_text", "") or ""))
                knowledge = self._sanitize_memory_text(str(profile.get("knowledge_text", "") or ""))
                portrait_len = len(str(portrait or ""))
                knowledge_len = len(str(knowledge or ""))
                if portrait or knowledge:
                    # 融入主 system prompt，而非单独追加
                    # 重新构建包含画像的 system prompt
                    main_prompt = self._build_system_prompt(portrait=portrait, knowledge=knowledge)
                    self.messages[0]["content"] = main_prompt
                    profile_injected = True

        if is_new_runtime_session and self.user_id:
            system_prompt_full = "\n\n".join(
                str(msg.get("content", ""))
                for msg in self.messages
                if msg.get("role") == "system"
            )
            debug_details = {
                "is_new_runtime_session": is_new_runtime_session,
                "history_empty": history_empty,
                "history_count": len(history),
                "has_user_id": bool(self.user_id),
                "profile_loaded": profile_loaded,
                "profile_injected": profile_injected,
                "portrait_len": portrait_len,
                "knowledge_len": knowledge_len,
                "conversation_id": self.conversation_id,
                "system_prompt_full": system_prompt_full,
            }
            yield {
                "type": "db_operation",
                "operation": "memory_injection_check",
                "message": (
                    "memory_check "
                    f"new={is_new_runtime_session} "
                    f"history_empty={history_empty} "
                    f"profile_loaded={profile_loaded} "
                    f"profile_injected={profile_injected} "
                    f"portrait_len={portrait_len} "
                    f"knowledge_len={knowledge_len}\n"
                    f"SYSTEM_PROMPT_FULL (仅用户画像):\n{portrait}"
                ),
                "details": debug_details,
            }

        for msg in history[current_history_count:]:
            self.messages.append(msg)

        synced_history_count = sum(
            1 for msg in self.messages if msg.get("role") in {"user", "assistant"}
        )
        self.messages.append({"role": "user", "content": user_input})

        iteration = 0
        while True:
            iteration += 1
            queue = get_api_queue()
            tools = self.skill_system.build_tools_definition(self.activated_skills)
            if hasattr(queue, "submit_async"):
                response_stream = await queue.submit_async(
                    "llm",
                    self._create_completion_stream_async,
                    self.messages,
                    tools,
                )
            else:
                response_stream = await queue.submit(
                    "llm",
                    self._create_completion_stream_async,
                    self.messages,
                    tools,
                )

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": "",
                "tool_calls": None,
            }
            tool_calls_by_index: dict[int, dict[str, Any]] = {}

            async for chunk in response_stream:
                self._record_usage_data(getattr(chunk, "usage", None))
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if getattr(delta, "tool_calls", None):
                    if assistant_message["tool_calls"] is None:
                        assistant_message["tool_calls"] = []

                    for tool_call in delta.tool_calls:
                        index = getattr(tool_call, "index", None)
                        if index is None:
                            continue
                        if index not in tool_calls_by_index:
                            tool_calls_by_index[index] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }

                        tc = tool_calls_by_index[index]
                        if getattr(tool_call, "id", None):
                            tc["id"] = tool_call.id

                        fn = getattr(tool_call, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                tc["function"]["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                tc["function"]["arguments"] += fn.arguments
                                func_name = tc["function"]["name"]
                                if func_name in self.skill_system.available_skills:
                                    if func_name not in self.activated_skills:
                                        self.activated_skills.add(func_name)
                                        skill_info = self.skill_system.available_skills[func_name]
                                        yield {
                                            "type": "skill_call",
                                            "skill": func_name,
                                            "description": skill_info.description,
                                        }

                elif getattr(delta, "content", None):
                    assistant_message["content"] += delta.content
                    yield {"type": "delta", "content": delta.content}

            if tool_calls_by_index:
                assistant_message["tool_calls"] = [
                    tool_calls_by_index[idx] for idx in sorted(tool_calls_by_index.keys())
                ]

            self.messages.append(assistant_message)

            if assistant_message["tool_calls"]:
                # 参数在流式阶段可能是碎片，统一在此处按完整参数推送一次 tool_call。
                for tc in assistant_message["tool_calls"]:
                    func_name = tc.get("function", {}).get("name", "")
                    if func_name and func_name not in self.skill_system.available_skills:
                        yield {
                            "type": "tool_call",
                            "tool": func_name,
                            "arguments": tc.get("function", {}).get("arguments", ""),
                        }
                        if self._is_database_skill_system():
                            yield {
                                "type": "db_operation",
                                "operation": func_name,
                                "message": f"正在调用数据库: {func_name}",
                            }

                try:
                    tool_messages = await self._handle_tool_calls_async(assistant_message["tool_calls"]) or []
                except Exception as exc:
                    logger.exception(f"Tool call failed: {exc}")
                    yield {"type": "error", "message": f"工具调用失败: {str(exc)}"}
                    yield {"type": "done"}
                    return

                for tm in tool_messages:
                    tool_name = "unknown"
                    for tc in assistant_message["tool_calls"]:
                        if tc.get("id") == tm.get("tool_call_id"):
                            tool_name = tc.get("function", {}).get("name", "unknown")
                            break
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "result": tm.get("content", ""),
                    }
            else:
                # 对话完成后检查触发条件
                self.round_count += 1

                # 获取 AI 回复内容
                response = assistant_message.get("content", "")
                print(f"[DEBUG] user_id={self.user_id}, response={response[:50]}...")

                # 保存对话历史
                if self.user_id:
                    await self._history_manager.append(
                        [
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": response},
                        ],
                    )

                # 检查是否触发记忆形成（基于数据库消息数量）
                if self.user_id and (synced_history_count + 2) >= 5:
                    # synced_history_count 为当前轮开始前已同步的 user/assistant 条数，
                    # 本轮会新增 user + assistant 两条。
                    await self.form_memory()

                logger.info(
    f"Chat stream completed: iteration={iteration}, "
    f"tool_calls={'yes' if assistant_message['tool_calls'] else 'no'}, "
    f"response_len={len(assistant_message.get('content', ''))}"
)

                # 上下文压缩检查
                estimated = estimate_tokens(self.messages)
                budget_check = create_budget_check(self.config)
                result = budget_check.check(estimated)

                if result.action == BudgetAction.COMPACT_WARNING:
                    # 发送预警 SSE
                    yield {"type": "compact_warning", "message": "上下文即将优化..."}

                elif result.action == BudgetAction.COMPACT_TRIGGER:
                    # 执行压缩
                    yield {"type": "compact_start", "message": "正在优化上下文..."}
                    success = await self.apply_compact()
                    if success:
                        yield {"type": "compact_done", "message": "上下文已优化，对话继续"}
                    else:
                        yield {"type": "compact_error", "message": "上下文优化失败，对话继续"}

                yield {
                    "type": "done",
                    "usage": {
                        "prompt_tokens": self.usage_totals.get("prompt_tokens", 0),
                        "completion_tokens": self.usage_totals.get("completion_tokens", 0),
                        "total_tokens": self.usage_totals.get("total_tokens", 0),
                    },
                }
                return

    def _run_cleanup(self, cleanup_fn: Any) -> None:
        result = cleanup_fn()
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
                # 在异步上下文中，创建任务执行清理
                loop.create_task(result)
            except RuntimeError:
                # 没有运行中的 loop，使用 run
                asyncio.run(result)

    def close(self) -> None:
        self._run_cleanup(close_clients)
        self._run_cleanup(close_resources)
        self._run_cleanup(close_pool)
        self._run_cleanup(shutdown_tool_loop)

    def clear_history(self) -> None:
        """清空对话历史"""
        self.messages = []


    def _record_usage(self, response: Any) -> None:
        """累计本次运行的 token 使用量。"""
        usage = getattr(response, "usage", None)
        self._record_usage_data(usage)

    def _record_usage_data(self, usage: Any) -> None:
        """累计 usage 对象/字典中的 token 使用量。"""
        if usage is None:
            return

        def _value(obj: Any, key: str) -> int:
            if hasattr(obj, key):
                raw = getattr(obj, key)
            elif isinstance(obj, dict):
                raw = obj.get(key, 0)
            else:
                raw = 0
            try:
                return int(raw or 0)
            except (TypeError, ValueError):
                return 0

        self.usage_totals["prompt_tokens"] += _value(usage, "prompt_tokens")
        self.usage_totals["completion_tokens"] += _value(usage, "completion_tokens")
        total = _value(usage, "total_tokens")
        if total == 0:
            total = _value(usage, "prompt_tokens") + _value(usage, "completion_tokens")
        self.usage_totals["total_tokens"] += total

    def get_usage_summary(self) -> dict[str, int]:
        """返回本次运行累计 token 统计。"""
        return dict(self.usage_totals)

    def _check_verification_token(self, skill_name: str, response_content: str) -> bool:
        """
        检查回复是否包含正确的验证暗号

        Args:
            skill_name: 技能名称
            response_content: AI 回复内容

        Returns:
            是否包含正确的验证暗号
        """
        skill_info = self.skill_system.get_skill_info(skill_name)
        if not skill_info or not skill_info.verification_token:
            return False

        return skill_info.verification_token in response_content
