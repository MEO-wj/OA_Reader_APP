#!/usr/bin/env python3
"""导入通用文档到数据库

此脚本扫描文档目录中的 Markdown 和 JSON 文件，将其内容导入到 documents 表中，
包括使用大模型生成摘要和生成向量嵌入用于语义搜索。

使用方法:
    uv run python scripts/import_documents.py [docs_dir]

环境变量:
    OPENAI_API_KEY: OpenAI API 密钥（必需）
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME: 数据库配置
"""
import asyncio
import argparse
import sys
import openai
from pathlib import Path

# 允许以 `python scripts/import_documents.py` 方式运行时找到 `src` 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.db import get_pool
from src.config.settings import Config
from src.core.base_retrieval import generate_embedding
from src.core.hash_utils import compute_document_hash, normalize_document_content
from src.chat.prompts_runtime import (
    DOC_SUMMARY_SYSTEM_PROMPT,
    DOC_SUMMARY_USER_PROMPT_TEMPLATE,
)

DEFAULT_DOCUMENTS_DIR = Path("docs")


async def generate_summary(title: str, content: str) -> str:
    """使用大模型生成文档的摘要介绍

    Args:
        title: 文档标题
        content: 文档完整内容

    Returns:
        生成的摘要文本
    """
    config = Config.load()
    async with openai.AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url
    ) as client:
        prompt = DOC_SUMMARY_USER_PROMPT_TEMPLATE.format(title=title, content=content)

        response = await client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": DOC_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )

        if not response.choices or not response.choices[0].message.content:
            raise ValueError("API 返回空响应")
        return response.choices[0].message.content.strip()


async def import_document(file_path: Path) -> dict:
    """导入单个文档文件

    读取 Markdown 或 JSON 文件，提取标题和内容，使用大模型生成摘要，
    生成向量嵌入，存入数据库。

    Args:
        file_path: 文件路径

    Returns:
        {"title": str, "status": "success/skipped/error", "message": str}
    """
    try:
        # 根据文件扩展名读取内容
        if file_path.suffix == ".json":
            raw_content = file_path.read_text(encoding="utf-8")
            content = normalize_document_content(raw_content, "json")
            source_type = "json"
        else:
            content = file_path.read_text(encoding="utf-8")
            source_type = "markdown"

        if not content.strip():
            return {"title": file_path.name, "status": "error", "message": "文件为空"}

        # 使用文件名（去掉扩展名）作为标题
        title = file_path.stem

        # 使用大模型生成摘要
        print(f"  [生成摘要] {title[:50]}...")
        summary = await generate_summary(title, content)
        print(f"  [摘要完成] {len(summary)} 字符")

        # 计算内容哈希（用于幂等性检查）
        content_hash = compute_document_hash(content, source_type)

        # 生成 embedding
        print(f"  [生成向量]...")
        embedding_list = await generate_embedding(summary)
        # 转换为 pgvector 字符串格式: "[0.1,0.2,...]"
        embedding_str = "[" + ",".join(str(x) for x in embedding_list) + "]"
        print(f"  [向量完成]")

        # 存入数据库（使用 upsert 语法）
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO documents (title, content, summary, source_type, embedding, content_hash)
                VALUES ($1, $2, $3, $4, $5::vector, $6)
                ON CONFLICT (content_hash) DO UPDATE SET
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    summary = EXCLUDED.summary,
                    source_type = EXCLUDED.source_type,
                    embedding = EXCLUDED.embedding
            """, title, content, summary, source_type, embedding_str, content_hash)

        return {"title": title, "status": "success", "message": "导入成功"}

    except Exception as e:
        return {"title": file_path.name, "status": "error", "message": str(e)}


async def filter_files_not_in_db(all_files: list[Path]) -> list[Path]:
    """根据数据库中的 content_hash 过滤已导入文件。"""
    file_hash_pairs: list[tuple[Path, str]] = []

    for file_path in all_files:
        try:
            source_type = "json" if file_path.suffix.lower() == ".json" else "markdown"
            raw_content = file_path.read_text(encoding="utf-8")
            content = normalize_document_content(
                raw_content,
                source_type,
                tolerate_invalid_json=True,
            )
            file_hash_pairs.append((file_path, compute_document_hash(content, source_type, tolerate_invalid_json=True)))
        except (OSError, ValueError):
            # 读取失败的文件保留在导入列表中，由 import_document 返回详细错误
            file_hash_pairs.append((file_path, ""))

    hash_values = [content_hash for _, content_hash in file_hash_pairs if content_hash]
    if not hash_values:
        return all_files

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content_hash
                FROM documents
                WHERE content_hash = ANY($1::text[])
                """,
                hash_values
            )
        existing_hashes = {row["content_hash"] for row in rows if row["content_hash"]}
    except Exception as exc:
        print(f"警告：无法读取数据库已导入记录，回退为目录全量导入。原因: {exc}")
        return all_files

    return [
        file_path
        for file_path, content_hash in file_hash_pairs
        if not content_hash or content_hash not in existing_hashes
    ]


async def main(documents_dir: Path | None = None):
    """主函数：扫描文档目录并导入所有文件

    扫描指定目录下的所有 .md 和 .json 文件，
    逐个导入到数据库中，并显示进度和统计信息。
    """
    documents_dir = documents_dir or DEFAULT_DOCUMENTS_DIR

    if not documents_dir.exists():
        print(f"错误：文档目录不存在: {documents_dir}")
        return

    # 收集所有文档文件
    md_files = sorted(documents_dir.glob("**/*.md"))
    json_files = sorted(documents_dir.glob("**/*.json"))
    all_files = md_files + json_files

    files_to_import = await filter_files_not_in_db(all_files)
    print(f"增量模式：扫描到 {len(all_files)} 个文档文件，待导入 {len(files_to_import)} 个")

    if not files_to_import:
        print("数据库中已存在全部文档文件，无需导入。")
        return

    print(f"找到 {len(files_to_import)} 个文档文件")

    results = []
    for i, file_path in enumerate(files_to_import, 1):
        print(f"[{i}/{len(files_to_import)}] 正在导入: {file_path.name}")
        result = await import_document(file_path)
        results.append(result)

        if result["status"] == "success":
            print(f"  成功: {result['title']}")
        else:
            print(f"  失败: {result['title']}: {result['message']}")

    # 统计
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = len(results) - success_count

    print(f"\n导入完成！成功: {success_count}, 失败: {error_count}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入文档到数据库")
    parser.add_argument("dir", nargs="?", type=Path, default=DEFAULT_DOCUMENTS_DIR,
                        help=f"文档目录路径 (默认: {DEFAULT_DOCUMENTS_DIR})")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.dir))
