"""自动导入决策器。

通用化版本：仅检查 skills 数据源的导入需求。
"""

from __future__ import annotations

from src.api.import_probe import needs_skill_import


async def should_run_auto_import() -> bool:
    """skills 数据集缺失/变更时返回 True。"""
    return await needs_skill_import()
