"""
TDD: 可视化输出模块单元测试

RED 阶段 - 测试先于实现
"""
import pytest
from io import StringIO


class TestColors:
    """颜色常量测试"""

    def test_color_codes_defined(self):
        """
        RED #1: 颜色常量定义完整
        Given: 导入 Colors 类
        When: 访问颜色属性
        Then: 所有 ANSI 颜色码都有定义
        """
        from src.ui.console import Colors

        assert hasattr(Colors, "HEADER")
        assert hasattr(Colors, "BLUE")
        assert hasattr(Colors, "CYAN")
        assert hasattr(Colors, "GREEN")
        assert hasattr(Colors, "YELLOW")
        assert hasattr(Colors, "RED")
        assert hasattr(Colors, "END")
        assert hasattr(Colors, "BOLD")

    def test_color_values_are_strings(self):
        """
        RED #2: 颜色值是字符串
        Given: Colors 类
        When: 访问任意颜色
        Then: 返回字符串
        """
        from src.ui.console import Colors

        assert isinstance(Colors.RED, str)
        assert isinstance(Colors.GREEN, str)
        assert isinstance(Colors.END, str)


class TestPrintFunctions:
    """打印函数测试"""

    def test_print_step_output(self, capsys):
        """
        RED #3: print_step 输出格式正确
        Given: 调用 print_step("🔍", "测试", "详情")
        When: 捕获输出
        Then: 包含分隔符、emoji 和标题
        """
        from src.ui.console import print_step

        print_step("🔍", "测试标题", "测试详情")

        captured = capsys.readouterr()
        output = captured.out

        assert "═" in output
        assert "🔍" in output
        assert "测试标题" in output
        assert "测试详情" in output

    def test_print_skill_loaded(self, capsys):
        """
        RED #4: print_skill_loaded 输出技能信息
        Given: 技能名称和内容
        When: 调用 print_skill_loaded
        Then: 输出包含名称和长度
        """
        from src.ui.console import print_skill_loaded

        print_skill_loaded("test-skill", "这是内容" * 10)

        captured = capsys.readouterr()
        output = captured.out

        assert "SKILL.md" in output
        assert "test-skill" in output
        assert "字符" in output

    def test_print_verification_token(self, capsys):
        """
        RED #5: print_verification_token 显示暗号
        Given: 一个验证暗号
        When: 调用 print_verification_token
        Then: 输出包含暗号文本
        """
        from src.ui.console import print_verification_token

        print_verification_token("TEST-TOKEN-123")

        captured = capsys.readouterr()
        output = captured.out

        assert "验证暗号" in output
        assert "TEST-TOKEN-123" in output

    def test_print_success(self, capsys):
        """
        RED #6: print_success 输出成功消息
        Given: 成功消息文本
        When: 调用 print_success
        Then: 输出包含✓图标和消息
        """
        from src.ui.console import print_success

        print_success("操作成功")

        captured = capsys.readouterr()
        output = captured.out

        assert "✅" in output
        assert "操作成功" in output

    def test_print_error(self, capsys):
        """
        RED #7: print_error 输出错误消息
        Given: 错误消息文本
        When: 调用 print_error
        Then: 输出包含❌图标和消息
        """
        from src.ui.console import print_error

        print_error("发生错误")

        captured = capsys.readouterr()
        output = captured.out

        assert "❌" in output
        assert "发生错误" in output
