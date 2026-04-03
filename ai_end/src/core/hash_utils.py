"""统一哈希工具模块。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_text(content: str) -> str:
    """计算文本的 SHA256 哈希。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_document_content(
    content: str,
    source_type: str,
    *,
    tolerate_invalid_json: bool = False,
) -> str:
    """规范化文档内容，确保不同入口哈希语义一致。"""
    if source_type.lower() != "json":
        return content

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        if tolerate_invalid_json:
            return content
        raise ValueError("JSON 内容格式错误")

    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_document_hash(
    content: str,
    source_type: str,
    *,
    tolerate_invalid_json: bool = False,
) -> str:
    """计算文档内容哈希（JSON 走标准化后再哈希）。"""
    normalized = normalize_document_content(
        content,
        source_type,
        tolerate_invalid_json=tolerate_invalid_json,
    )
    return hash_text(normalized)


def hash_path(path: Path) -> str:
    """计算文件内容的 SHA256 哈希。"""
    return hash_text(path.read_text(encoding="utf-8"))


def hash_directory(directory: Path, extensions: set[str] | None = None) -> str:
    """
    计算目录的哈希（文件名+内容）。

    Args:
        directory: 要哈希的目录
        extensions: 要包含的文件扩展名（默认 .json, .csv）

    Returns:
        目录的 SHA256 哈希值
    """
    if extensions is None:
        extensions = {".json", ".csv"}

    files = sorted(
        [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in extensions],
        key=lambda p: p.name,
    )
    parts: list[str] = []
    for f in files:
        parts.append(f.name)
        parts.append(f.read_text(encoding="utf-8"))
    return hash_text("\n<split>\n".join(parts))
