"""
上下文预算监控模块（方案 C-1 + C-2）

提供 token 预估、预算检查和决策逻辑。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any


class BudgetAction(Enum):
    """预算检查结果动作"""
    OK = "ok"           # 正常执行
    WARNING = "warning"  # 记录警告，提示用户
    CRITICAL = "critical"  # 严重警告，建议压缩历史
    BLOCK = "block"     # 拒绝请求，提示开新会话
    COMPACT_WARNING = "compact_warning"  # 上下文接近上限，需要优化
    COMPACT_TRIGGER = "compact_trigger"  # 触发压缩


@dataclass
class BudgetResult:
    """预算检查结果"""
    action: BudgetAction
    usage_ratio: float  # 占用率 (0.0 - 1.0)
    estimated_tokens: int
    message: str  # 人类可读的消息


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """
    从消息列表估算 token 数量。

    使用粗略估算：字符数 / 3（适合中文场景）。
    英文场景约 4 字符/token，但混合场景 3 是一个合理的中间值。

    Args:
        messages: 消息列表

    Returns:
        估算的 token 数量
    """
    if not messages:
        return 0

    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if content:
            total_chars += len(str(content))

        # 计算 tool_calls 的开销（如果有）
        if msg.get("tool_calls"):
            # 每个 tool_call 约 50-100 tokens
            total_chars += len(msg.get("tool_calls", [])) * 150

    # 字符数 / 3 作为粗略估算
    return total_chars // 3


class BudgetCheck:
    """
    上下文预算检查器

    阈值设计（两套阈值体系）：
    - 通用阈值（用于通用操作建议）：
      - <75%: OK - 正常执行
      - 75%-86%: WARNING - 记录警告
      - 86%-95%: CRITICAL - 建议压缩
      - >95%: BLOCK - 拒绝请求
    - Compact 阈值（用于上下文压缩决策，enable_auto_compact=True 时生效）：
      - 70%-86%: COMPACT_WARNING - 需要优化
      - >85%: COMPACT_TRIGGER - 触发压缩
    """

    # 默认阈值（通用阈值体系）
    WARNING_THRESHOLD = 0.75
    CRITICAL_THRESHOLD = 0.90  # 90% - 确保 90%+ 区间返回 CRITICAL
    BLOCK_THRESHOLD = 0.95

    # Compact 触发阈值（独立阈值体系，用于上下文压缩）
    # 这套阈值独立于通用阈值，专门用于判断是否需要触发上下文压缩
    COMPACT_WARNING_THRESHOLD = 0.70  # 70% 开始预警
    COMPACT_TRIGGER_THRESHOLD = 0.85  # 85% 触发压缩（85-90% 区间）

    def __init__(
        self,
        max_tokens: int = 16000,
        warning_threshold: float = WARNING_THRESHOLD,
        critical_threshold: float = CRITICAL_THRESHOLD,
        block_threshold: float = BLOCK_THRESHOLD,
        compact_warning_threshold: float = COMPACT_WARNING_THRESHOLD,
        compact_trigger_threshold: float = COMPACT_TRIGGER_THRESHOLD,
        enable_auto_compact: bool = True,  # C-2: 是否启用自动压缩
    ):
        """
        初始化预算检查器

        Args:
            max_tokens: 最大 token 数量（模型上下文上限）
            warning_threshold: 警告阈值 (0-1)
            critical_threshold: 严重阈值 (0-1)
            block_threshold: 拦截阈值 (0-1)
            compact_warning_threshold: 压缩预警阈值 (0-1)
            compact_trigger_threshold: 压缩触发阈值 (0-1)
            enable_auto_compact: 是否启用自动压缩（C-2）
        """
        self.max_tokens = max_tokens
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.block_threshold = block_threshold
        self.compact_warning_threshold = compact_warning_threshold
        self.compact_trigger_threshold = compact_trigger_threshold
        self.enable_auto_compact = enable_auto_compact

    def check(self, estimated_tokens: int) -> BudgetResult:
        """
        检查预算状态

        Args:
            estimated_tokens: 估算的 token 数量

        Returns:
            BudgetResult 包含动作和消息
        """
        usage_ratio = estimated_tokens / self.max_tokens

        if usage_ratio >= self.block_threshold:
            return BudgetResult(
                action=BudgetAction.BLOCK,
                usage_ratio=usage_ratio,
                estimated_tokens=estimated_tokens,
                message=f"对话过长（已使用 {usage_ratio*100:.1f}%），请开始新对话"
            )

        if usage_ratio >= self.critical_threshold:
            return BudgetResult(
                action=BudgetAction.CRITICAL,
                usage_ratio=usage_ratio,
                estimated_tokens=estimated_tokens,
                message=f"上下文接近上限（{usage_ratio*100:.1f}%），建议清空历史或开始新对话"
            )

        # Compact 相关检查（使用独立的 compact 阈值）
        # 仅 compact_trigger 受 enable_auto_compact 控制
        # 注意：此检查位于 critical 之后，确保 85-90% 区间返回 COMPACT_TRIGGER
        if self.enable_auto_compact and usage_ratio >= self.compact_trigger_threshold:
            return BudgetResult(
                action=BudgetAction.COMPACT_TRIGGER,
                usage_ratio=usage_ratio,
                estimated_tokens=estimated_tokens,
                message=f"上下文使用率过高（{usage_ratio*100:.1f}%），触发压缩"
            )

        if usage_ratio >= self.warning_threshold:
            return BudgetResult(
                action=BudgetAction.WARNING,
                usage_ratio=usage_ratio,
                estimated_tokens=estimated_tokens,
                message=f"上下文使用率较高（{usage_ratio*100:.1f}%），可能影响性能"
            )

        if usage_ratio >= self.compact_warning_threshold:
            return BudgetResult(
                action=BudgetAction.COMPACT_WARNING,
                usage_ratio=usage_ratio,
                estimated_tokens=estimated_tokens,
                message=f"上下文使用率渐高（{usage_ratio*100:.1f}%），建议优化"
            )

        return BudgetResult(
            action=BudgetAction.OK,
            usage_ratio=usage_ratio,
            estimated_tokens=estimated_tokens,
            message=f"上下文正常（{usage_ratio*100:.1f}%）"
        )


def create_budget_check(config: Any = None) -> BudgetCheck:
    """
    工厂函数：创建预算检查器

    Args:
        config: 配置对象（可选），支持以下属性：
            - max_tokens: 最大 token 数量
            - enable_auto_compact: 是否启用自动压缩

    Returns:
        BudgetCheck 实例
    """
    if config is not None:
        max_tokens = getattr(config, "max_tokens", 16000)
        enable_auto_compact = getattr(config, "enable_auto_compact", True)
    else:
        max_tokens = 16000
        enable_auto_compact = True
    return BudgetCheck(max_tokens=max_tokens, enable_auto_compact=enable_auto_compact)


def should_compact(
    usage_ratio: float,
    compact_trigger_threshold: float = BudgetCheck.COMPACT_TRIGGER_THRESHOLD,
    compact_warning_threshold: float = BudgetCheck.COMPACT_WARNING_THRESHOLD,
) -> tuple[bool, str]:
    """
    判断是否需要触发 compact，返回 (是否需要, 原因)

    Args:
        usage_ratio: 使用率 (0.0 - 1.0)
        compact_trigger_threshold: 压缩触发阈值
        compact_warning_threshold: 压缩预警阈值

    Returns:
        tuple[bool, str]: (是否需要compact, 原因描述)
    """
    if usage_ratio >= compact_trigger_threshold:
        return (True, f"使用率 {usage_ratio*100:.1f}% 超过触发阈值 {compact_trigger_threshold*100:.1f}%")
    if usage_ratio >= compact_warning_threshold:
        return (True, f"使用率 {usage_ratio*100:.1f}% 达到预警阈值 {compact_warning_threshold*100:.1f}%")
    return (False, f"使用率 {usage_ratio*100:.1f}% 无需触发 compact")


def get_compact_threshold() -> float:
    """
    返回 compact 触发阈值

    Returns:
        float: compact 触发阈值 (0-1)
    """
    return BudgetCheck.COMPACT_TRIGGER_THRESHOLD


# 已移除 compact_messages 等压缩功能，恢复原有简单实现
