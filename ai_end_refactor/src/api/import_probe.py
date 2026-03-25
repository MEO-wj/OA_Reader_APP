"""启动阶段的导入探测逻辑。

仅做本地数据扫描和数据库对比，不触发外部 API 调用。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.core.db import get_pool
from src.core.hash_utils import compute_document_hash, hash_text

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_DIR = Path("skills")
DEFAULT_DOCUMENTS_DIR = Path("docs")


def _compute_document_hash(file_path: Path) -> str:
    """计算文档哈希（与导入链路保持一致）。"""
    content = file_path.read_text(encoding="utf-8")
    source_type = "json" if file_path.suffix.lower() == ".json" else "markdown"
    return compute_document_hash(
        content,
        source_type,
        tolerate_invalid_json=True,
    )


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


async def _check_hashes_exist(table: str, hash_column: str, hashes: list[str]) -> set[str]:
    """
    检查哪些哈希值已存在于数据库中。

    Args:
        table: 表名
        hash_column: 哈希列名
        hashes: 要检查的哈希值列表

    Returns:
        存在的哈希值集合
    """
    if not hashes:
        return set()

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {hash_column} FROM {table} WHERE {hash_column} = ANY($1::text[])",
            hashes,
        )
    return {row[hash_column] for row in rows if row[hash_column]}


async def needs_document_import(documents_dir: Path = DEFAULT_DOCUMENTS_DIR) -> bool:
    """检查 documents 是否需要导入。

    扫描 documents 目录下所有 .md 和 .json 文件，检查是否有新增或变更。

    Args:
        documents_dir: 文档目录路径

    Returns:
        是否需要导入
    """
    if not documents_dir.exists():
        return False

    # 收集所有文档文件
    md_files = sorted(documents_dir.glob("**/*.md"))
    json_files = sorted(documents_dir.glob("**/*.json"))

    all_files = md_files + json_files
    if not all_files:
        return False

    # 计算所有文件的哈希
    hashes = []
    for f in all_files:
        h = _compute_document_hash(f)
        hashes.append(h)

    try:
        existing = await _check_hashes_exist("documents", "content_hash", hashes)
    except Exception:
        logger.exception("检查文档导入状态时出错")
        return True

    # 如果有任何文件不在数据库中，需要导入
    return any(h not in existing for h in hashes)


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


