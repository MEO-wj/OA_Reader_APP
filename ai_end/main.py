#!/usr/bin/env python3
"""
通用 AI Agent 后端 - 分层架构版

基于技能系统的通用文档检索助手
"""
import asyncio
from src.config import Config
from src.ui import (
    Colors, print_step, print_success, print_error
)
from src.chat import ChatClient
from src.di.providers import get_chat_client


def print_banner(config):
    """打印欢迎横幅和配置信息"""
    print(f"""
{Colors.BOLD}{Colors.CYAN}
通用 AI Agent 后端
技能调用验证系统
{Colors.END}
    """)
    print(f"{Colors.CYAN}配置信息:{Colors.END}")
    print(f"  API 地址: {Colors.BOLD}{config.base_url}{Colors.END}")
    print(f"  模型: {Colors.BOLD}{config.model}{Colors.END}")
    print(f"  技能目录: {config.skills_dir}")
    print()


def print_commands():
    """打印可用命令"""
    print(f"{Colors.CYAN}命令:{Colors.END}")
    print(f"  直接输入问题与 AI 对话")
    print(f"  'skills' 或 'list' - 查看可用技能")
    print(f"  'verify <skill_name>' - 验证特定技能")
    print(f"  'quit' 或 'exit' - 退出\n")


def print_ai_reply(content: str):
    """打印 AI 回复"""
    print(f"\n{Colors.BLUE}🤖 AI 回复:{Colors.END}")
    print(f"{Colors.BLUE}{'─' * 40}{Colors.END}")
    print(content)
    print(f"{Colors.BLUE}{'─' * 40}{Colors.END}")


def handle_list_skills(client: ChatClient):
    """处理查看技能列表命令"""
    print_step("📋", "可用技能列表")
    for name, info in client.skill_system.available_skills.items():
        print(f"\n{Colors.CYAN}• {Colors.BOLD}{name}{Colors.END}")
        print(f"  {info.description}")
        if info.verification_token:
            print(f"  {Colors.YELLOW}验证暗号: {info.verification_token}{Colors.END}")


def handle_verify_skill(client: ChatClient, skill_name: str):
    """处理验证技能命令"""
    info = client.skill_system.get_skill_info(skill_name)
    if info:
        print_step("🔐", f"验证技能: {skill_name}")
        if info.verification_token:
            print_success(f"验证暗号: {info.verification_token}")
            print_warning(f"请在对话中要求 AI 说出这个暗号来验证它真的使用了这个 skill")
        else:
            print_warning("此技能没有设置验证暗号")
    else:
        print_error(f"技能不存在: {skill_name}")


def print_warning(message: str):
    """打印警告（临时添加，可考虑移到 ui 模块）"""
    print(f"\n{Colors.YELLOW}⚠️  {message}{Colors.END}")


def print_usage_summary(client: ChatClient):
    """打印本次运行累计 token 使用量。"""
    summary = client.get_usage_summary()
    total = summary.get("total_tokens", 0)
    prompt = summary.get("prompt_tokens", 0)
    completion = summary.get("completion_tokens", 0)

    print(f"\n{Colors.CYAN}本次运行 Token 使用统计:{Colors.END}")
    print(f"  prompt: {Colors.BOLD}{prompt}{Colors.END}")
    print(f"  completion: {Colors.BOLD}{completion}{Colors.END}")
    print(f"  总计: {Colors.BOLD}{total}{Colors.END}")


def check_verification_tokens(client: ChatClient, response: str):
    """检查回复中是否包含验证暗号"""
    for skill_name, skill_info in client.skill_system.available_skills.items():
        if skill_info.verification_token and skill_info.verification_token in response:
            print_success(f"✨ 验证通过！AI 确实使用了技能 [{skill_name}]，回复中包含验证暗号")
            break


async def main_async():
    """主函数（异步）"""
    # 加载配置
    config = Config.load()

    client = get_chat_client(config)

    # 显示欢迎信息
    print_banner(config)
    print_commands()

    try:
        # 主循环
        while True:
            user_input = input(f"\n{Colors.BOLD}User:{Colors.END} ").strip()

            # 退出命令
            if user_input.lower() in ['quit', 'exit', 'q']:
                print_usage_summary(client)
                print(f"\n{Colors.GREEN}再见！{Colors.END}\n")
                break

            # 空输入跳过
            if not user_input:
                continue

            # 查看技能列表命令
            if user_input.lower() in ['skills', 'list']:
                handle_list_skills(client)
                continue

            # 验证技能命令
            if user_input.lower().startswith('verify '):
                skill_name = user_input.split(' ', 1)[1]
                handle_verify_skill(client, skill_name)
                continue

            # 正常对话
            print_step("👤", "用户输入", user_input)
            response = client.chat(user_input)
            print_ai_reply(response)

            # 检查验证暗号
            check_verification_tokens(client, response)

    except KeyboardInterrupt:
        print_usage_summary(client)
        print(f"\n{Colors.GREEN}再见！{Colors.END}\n")
    except Exception as e:
        print_error(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理资源（顺序：close_clients → close_resources → close_pool → shutdown_tool_loop）
        client.close()


def main():
    """入口函数"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
