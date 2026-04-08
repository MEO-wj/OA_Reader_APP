"""
可视化输出工具 - 终端颜色和格式化输出

TDD GREEN 阶段：编写最小代码通过测试
"""


class Colors:
    """终端 ANSI 颜色码"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_step(step_emoji, step_name, detail=""):
    """打印步骤标题"""
    color = Colors.CYAN
    print(f"\n{color}{Colors.BOLD}{'═' * 60}{Colors.END}")
    print(f"{color}{Colors.BOLD}{step_emoji} {step_name}{Colors.END}")
    if detail:
        print(f"{color}{detail}{Colors.END}")
    print(f"{color}{Colors.BOLD}{'═' * 60}{Colors.END}")


def print_skill_loaded(skill_name, content_preview):
    """打印技能加载"""
    print(f"\n{Colors.GREEN}📄 SKILL.md 已载入上下文{Colors.END}")
    print(f"{Colors.GREEN}   技能名称: {Colors.BOLD}{skill_name}{Colors.END}")
    print(f"{Colors.GREEN}   内容长度: {len(content_preview)} 字符{Colors.END}")
    print(f"{Colors.GREEN}   内容预览: {Colors.END}{content_preview[:100]}...")


def print_verification_token(token):
    """打印验证暗号"""
    print(f"\n{Colors.YELLOW}🔐 验证暗号: {Colors.BOLD}{token}{Colors.END}")
    print(f"{Colors.YELLOW}   ⚠️ 如果 AI 回复中不包含此暗号，说明它没有真正使用 skill！{Colors.END}")


def print_success(message):
    """打印成功消息"""
    print(f"\n{Colors.GREEN}✅ {message}{Colors.END}")


def print_error(message):
    """打印错误"""
    print(f"\n{Colors.RED}❌ {message}{Colors.END}")
