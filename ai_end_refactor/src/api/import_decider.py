"""自动导入决策器。

通用化版本：仅检查 skills 和 documents 两个数据源的导入需求。
"""

from __future__ import annotations

import asyncio

from src.api.import_probe import (
    needs_document_import,
    needs_skill_import,
)


async def should_run_auto_import() -> bool:
    """任一数据集（skills 或 documents）缺失/变更时返回 True。"""
    checks = await asyncio.gather(
        needs_skill_import(),
        needs_document_import(),
    )
    return any(checks)
