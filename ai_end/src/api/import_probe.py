"""启动阶段的导入探测逻辑。

仅做本地数据扫描和数据库对比，不触发外部 API 调用。
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.db import get_pool
from src.core.hash_utils import hash_text

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_DIR = Path("skills")


def _compute_local_skill_fingerprint(skill_dir: Path) -> str:
    """计算技能目录的本地指纹（包含 SKILL.md、TOOLS.md、references）。"""
    parts: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    parts.append(skill_md.read_text(encoding="utf-8"))

    tools_md = skill_dir / "TOOLS.md"
    parts.append(tools_md.read_text(encoding="utf-8") if tools_md.exists() else "")

    references_dir = skill_dir / "references"
    if references_dir.exists() and references_dir.is_dir():
        for ref in sorted(p for p in references_dir.rglob("*") if p.is_file()):
            rel = ref.relative_to(references_dir).as_posix()
            parts.append(rel)
            parts.append(ref.read_text(encoding="utf-8"))

    return hash_text("\n<split>\n".join(parts))


async def needs_skill_import(skills_dir: Path = DEFAULT_SKILLS_DIR) -> bool:
    """检查技能是否需要导入。"""
    if not skills_dir.exists():
        return False

    skill_dirs = sorted(
        [d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()],
        key=lambda p: p.name,
    )
    if not skill_dirs:
        return False

    local_fingerprints = {d.name: _compute_local_skill_fingerprint(d) for d in skill_dirs}

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.name, s.content, s.tools, r.file_path, r.content AS ref_content
                FROM skills s
                LEFT JOIN skill_references r ON s.id = r.skill_id
                WHERE s.is_static = true
                ORDER BY s.name ASC, r.file_path ASC NULLS FIRST
                """
            )
    except Exception:
        logger.exception("检查技能导入状态时出错")
        return True

    db_parts: dict[str, list[str]] = {}
    for row in sorted(rows, key=lambda item: ((item["name"] or ""), (item["file_path"] or ""))):
        name = row["name"]
        if name not in db_parts:
            db_parts[name] = [row["content"] or "", row["tools"] or ""]
        if row["file_path"]:
            db_parts[name].append(row["file_path"])
            db_parts[name].append(row["ref_content"] or "")

    db_fingerprints: dict[str, str] = {}
    for name, parts in db_parts.items():
        db_fingerprints[name] = hash_text("\n<split>\n".join(parts))

    for name, local_hash in local_fingerprints.items():
        if name not in db_fingerprints:
            return True
        if db_fingerprints[name] != local_hash:
            return True

    return False
