"""
测试 src.chat.context_budget - 上下文预算监控模块

TDD 阶段：验证 compact 触发检测功能
"""
import pytest
from src.chat.context_budget import (
    BudgetAction,
    BudgetCheck,
    BudgetResult,
    should_compact,
    get_compact_threshold,
    create_budget_check,
)


class TestBudgetActionEnum:
    """测试 BudgetAction 枚举包含 compact 相关动作"""

    def test_compact_warning_exists(self):
        """COMPACT_WARNING 枚举值应存在"""
        assert hasattr(BudgetAction, 'COMPACT_WARNING')
        assert BudgetAction.COMPACT_WARNING.value == "compact_warning"

    def test_compact_trigger_exists(self):
        """COMPACT_TRIGGER 枚举值应存在"""
        assert hasattr(BudgetAction, 'COMPACT_TRIGGER')
        assert BudgetAction.COMPACT_TRIGGER.value == "compact_trigger"


class TestBudgetCheckThresholds:
    """测试 BudgetCheck 类的 compact 阈值"""

    def test_compact_warning_threshold_constant(self):
        """COMPACT_WARNING_THRESHOLD 应为 0.70"""
        assert BudgetCheck.COMPACT_WARNING_THRESHOLD == 0.70

    def test_compact_trigger_threshold_constant(self):
        """COMPACT_TRIGGER_THRESHOLD 应为 0.85"""
        assert BudgetCheck.COMPACT_TRIGGER_THRESHOLD == 0.85

    def test_custom_compact_thresholds(self):
        """BudgetCheck 应支持自定义 compact 阈值"""
        checker = BudgetCheck(
            max_tokens=10000,
            compact_warning_threshold=0.60,
            compact_trigger_threshold=0.80,
        )
        assert checker.compact_warning_threshold == 0.60
        assert checker.compact_trigger_threshold == 0.80


class TestBudgetCheckCompact:
    """测试 BudgetCheck.check() 方法的 compact 相关逻辑"""

    def test_warning_below_critical_threshold(self):
        """使用率 80% 应触发 WARNING（<86%）"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(8000)  # 80%
        assert result.action == BudgetAction.WARNING

    def test_critical_above_90_percent(self):
        """使用率 92% 应触发 CRITICAL（86-95% 区间，COMPACT_TRIGGER 之后）"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(9200)  # 92%
        assert result.action == BudgetAction.CRITICAL

    def test_compact_warning_at_70_percent(self):
        """使用率 70% 应触发 COMPACT_WARNING"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(7000)  # 70%
        assert result.action == BudgetAction.COMPACT_WARNING
        assert "建议优化" in result.message

    def test_compact_warning_between_70_and_75(self):
        """使用率 72% 应触发 COMPACT_WARNING（70%-75% 之间）"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(7200)  # 72%
        assert result.action == BudgetAction.COMPACT_WARNING

    def test_ok_below_70_percent(self):
        """使用率 69% 应返回 OK"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(6900)  # 69%
        assert result.action == BudgetAction.OK

    def test_priority_over_warning(self):
        """使用率 80% 时，compact_trigger (85%) 优先于 warning (75%)"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(8000)  # 80%
        # 80% < 85%, so it should be WARNING
        assert result.action == BudgetAction.WARNING

    def test_priority_critical_over_compact_trigger(self):
        """使用率 92% 时，critical (90%) 优先于 compact_trigger (85%)"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(9200)  # 92%
        assert result.action == BudgetAction.CRITICAL

    def test_critical_between_86_and_90_percent(self):
        """使用率 86-90% 区间应返回 COMPACT_TRIGGER（85-90% 区间）"""
        checker = BudgetCheck(max_tokens=10000)
        # 测试 86%
        result = checker.check(8600)
        assert result.action == BudgetAction.COMPACT_TRIGGER
        # 测试 88%
        result = checker.check(8800)
        assert result.action == BudgetAction.COMPACT_TRIGGER
        # 测试 89%
        result = checker.check(8900)
        assert result.action == BudgetAction.COMPACT_TRIGGER

    def test_priority_block_over_all(self):
        """使用率 96% 时，block (95%) 优先于所有其他动作"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(9600)  # 96%
        assert result.action == BudgetAction.BLOCK


class TestShouldCompact:
    """测试 should_compact 辅助函数"""

    def test_should_compact_trigger(self):
        """使用率 >= 90% 应返回 (True, 触发原因)"""
        should, reason = should_compact(0.91)
        assert should is True
        assert "触发阈值" in reason

    def test_should_compact_warning(self):
        """70% <= 使用率 < 85% 应返回 (True, 预警原因)"""
        should, reason = should_compact(0.75)
        assert should is True
        assert "预警阈值" in reason

    def test_should_not_compact(self):
        """使用率 < 70% 应返回 (False, 无需触发)"""
        should, reason = should_compact(0.50)
        assert should is False
        assert "无需触发" in reason

    def test_boundary_70_exactly(self):
        """使用率正好 70% 应该是 warning"""
        should, reason = should_compact(0.70)
        assert should is True
        assert "预警阈值" in reason

    def test_boundary_90_exactly(self):
        """使用率正好 90% 应该是 trigger"""
        should, reason = should_compact(0.90)
        assert should is True
        assert "触发阈值" in reason


class TestGetCompactThreshold:
    """测试 get_compact_threshold 辅助函数"""

    def test_returns_trigger_threshold(self):
        """应返回 COMPACT_TRIGGER_THRESHOLD 值"""
        threshold = get_compact_threshold()
        assert threshold == BudgetCheck.COMPACT_TRIGGER_THRESHOLD
        assert threshold == 0.85


class TestExistingFunctionality:
    """确保现有功能未受影响"""

    def test_ok_action_still_works(self):
        """OK 动作应正常工作"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(5000)  # 50%
        assert result.action == BudgetAction.OK
        assert result.usage_ratio == 0.5

    def test_warning_action_still_works(self):
        """WARNING 动作应正常工作"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(8000)  # 80%
        assert result.action == BudgetAction.WARNING

    def test_critical_action_still_works(self):
        """CRITICAL 动作应正常工作"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(9300)  # 93%
        assert result.action == BudgetAction.CRITICAL

    def test_block_action_still_works(self):
        """BLOCK 动作应正常工作"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(9800)  # 98%
        assert result.action == BudgetAction.BLOCK

    def test_create_budget_check_factory(self):
        """create_budget_check 工厂函数应正常工作"""
        checker = create_budget_check()
        assert isinstance(checker, BudgetCheck)
        assert checker.max_tokens == 16000
        assert checker.enable_auto_compact is True


class TestBudgetResult:
    """测试 BudgetResult 数据类"""

    def test_compact_warning_result(self):
        """COMPACT_WARNING 应返回完整的 BudgetResult"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(7200)
        assert isinstance(result, BudgetResult)
        assert result.action == BudgetAction.COMPACT_WARNING
        assert result.usage_ratio == pytest.approx(0.72)
        assert result.estimated_tokens == 7200
        assert "72.0%" in result.message

    def test_critical_result_at_88_percent(self):
        """88% 应返回 COMPACT_TRIGGER（85-90% 区间）"""
        checker = BudgetCheck(max_tokens=10000)
        result = checker.check(8800)
        assert isinstance(result, BudgetResult)
        assert result.action == BudgetAction.COMPACT_TRIGGER
        assert result.usage_ratio == pytest.approx(0.88)
        assert result.estimated_tokens == 8800
        assert "88.0%" in result.message
